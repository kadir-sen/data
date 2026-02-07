"""Normalization pipeline job.

Reads unprocessed raw_events, maps them through source-specific mappers,
upserts canonical entities, runs cross-system linking, and validates.

Usage:
    python -m app.jobs.normalize --since 2024-01-01T00:00:00Z
    python -m app.jobs.normalize --since 2024-01-01 --dry-run
    python -m app.jobs.normalize --since 2024-01-01 --validate-only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.jobs.linker import auto_link_from_text, upsert_external_link
from app.jobs.mappers import MAPPER_REGISTRY, MapperResult
from app.jobs.validators import ValidationReport, validate_post_normalize
from app.models.doc_entry import DocEntry
from app.models.interaction_event import InteractionEvent
from app.models.person import Person
from app.models.raw_event import RawEvent
from app.models.sprint import Sprint
from app.models.work_item import WorkItem

logger = logging.getLogger(__name__)

# ── statistics ────────────────────────────────────────────────────────


class NormalizeStats:
    """Tracks normalization run statistics."""

    def __init__(self) -> None:
        self.raw_events_processed = 0
        self.raw_events_skipped = 0
        self.raw_events_errored = 0
        self.persons_upserted = 0
        self.sprints_upserted = 0
        self.work_items_upserted = 0
        self.doc_entries_upserted = 0
        self.interactions_upserted = 0
        self.links_created = 0
        self.auto_links_from_text = 0

    def summary(self) -> dict[str, int]:
        return {
            "raw_events_processed": self.raw_events_processed,
            "raw_events_skipped": self.raw_events_skipped,
            "raw_events_errored": self.raw_events_errored,
            "persons_upserted": self.persons_upserted,
            "sprints_upserted": self.sprints_upserted,
            "work_items_upserted": self.work_items_upserted,
            "doc_entries_upserted": self.doc_entries_upserted,
            "interactions_upserted": self.interactions_upserted,
            "links_created": self.links_created,
            "auto_links_from_text": self.auto_links_from_text,
        }


# ── core pipeline ─────────────────────────────────────────────────────


async def normalize(
    since: datetime,
    dry_run: bool = False,
    batch_size: int = 500,
) -> tuple[NormalizeStats, ValidationReport | None]:
    """Main normalization entry point.

    Args:
        since: Only process raw_events with occurred_at >= since.
        dry_run: If True, do not commit changes to DB.
        batch_size: Number of raw_events to process per batch.

    Returns:
        Tuple of (stats, validation_report).
    """
    stats = NormalizeStats()

    async with async_session() as session:
        offset = 0
        while True:
            # Fetch next batch of unprocessed raw_events
            stmt = (
                select(RawEvent)
                .where(
                    RawEvent.occurred_at >= since,
                    RawEvent.error.is_(None),
                )
                .order_by(RawEvent.occurred_at)
                .offset(offset)
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                break

            for event in events:
                await _process_event(session, event, stats, dry_run)

            if not dry_run:
                await session.commit()

            offset += batch_size
            logger.info(
                "Processed batch: offset=%d, cumulative=%d events",
                offset, stats.raw_events_processed,
            )

        # Run validation after all processing
        report = None
        if not dry_run:
            report = await validate_post_normalize(session)

    return stats, report


async def _process_event(
    session: AsyncSession,
    event: RawEvent,
    stats: NormalizeStats,
    dry_run: bool,
) -> None:
    """Process a single raw_event through the appropriate mapper."""
    mapper_cls = MAPPER_REGISTRY.get(event.source)
    if not mapper_cls:
        stats.raw_events_skipped += 1
        logger.debug("No mapper for source=%s, skipping event %s", event.source, event.id)
        return

    mapper = mapper_cls()
    try:
        result = mapper.map(event.entity_type, event.entity_id, event.payload)
    except Exception as exc:
        stats.raw_events_errored += 1
        logger.exception("Mapper failed for event %s: %s", event.id, exc)
        if not dry_run:
            await session.execute(
                update(RawEvent)
                .where(RawEvent.id == event.id)
                .values(error=f"Mapper error: {exc}")
            )
        return

    if result.has_errors:
        stats.raw_events_errored += 1
        error_msg = "; ".join(result.errors)
        logger.warning("Mapper returned errors for event %s: %s", event.id, error_msg)
        if not dry_run:
            await session.execute(
                update(RawEvent)
                .where(RawEvent.id == event.id)
                .values(error=error_msg)
            )
        return

    if dry_run:
        stats.raw_events_processed += 1
        return

    # Upsert entities in dependency order: persons -> sprints -> work_items -> docs -> interactions
    person_id_map = await _upsert_persons(session, result.persons, stats)
    sprint_id_map = await _upsert_sprints(session, result.sprints, stats)
    work_item_id_map = await _upsert_work_items(
        session, result.work_items, person_id_map, sprint_id_map, stats
    )
    doc_id_map = await _upsert_doc_entries(session, result.doc_entries, person_id_map, stats)
    await _upsert_interactions(
        session, result.interaction_events, person_id_map, work_item_id_map, doc_id_map, stats
    )

    # Process external links from mapper
    for link_data in result.external_links:
        canonical_table = link_data["canonical_table"]
        # Resolve the canonical_id from the appropriate map
        id_maps = {
            "work_item": work_item_id_map,
            "sprint": sprint_id_map,
            "person": person_id_map,
            "doc_entry": doc_id_map,
        }
        source_id = link_data["external_id"]
        id_map = id_maps.get(canonical_table, {})
        canonical_key = f"{link_data['source']}:{source_id}"
        canonical_id = id_map.get(canonical_key)
        if canonical_id:
            await upsert_external_link(
                session,
                canonical_table=canonical_table,
                canonical_id=canonical_id,
                source=link_data["source"],
                external_id=source_id,
                external_url=link_data.get("external_url"),
                link_type=link_data.get("link_type", "auto"),
                confidence=link_data.get("confidence"),
            )
            stats.links_created += 1

    # Auto-link from text (descriptions, bodies)
    for wi_data in result.work_items:
        desc = wi_data.get("description", "")
        if desc:
            canonical_key = f"{wi_data['source']}:{wi_data['source_id']}"
            wi_id = work_item_id_map.get(canonical_key)
            if wi_id:
                n = await auto_link_from_text(session, desc, "work_item", wi_id)
                stats.auto_links_from_text += n

    stats.raw_events_processed += 1


# ── upsert helpers ────────────────────────────────────────────────────


async def _upsert_persons(
    session: AsyncSession,
    persons: list[dict[str, Any]],
    stats: NormalizeStats,
) -> dict[str, uuid.UUID]:
    """Upsert persons, returns mapping of 'source:source_id' -> person UUID."""
    id_map: dict[str, uuid.UUID] = {}
    seen: set[str] = set()

    for p in persons:
        source = p.get("source", "")
        source_id = p.get("source_id", "")
        key = f"{source}:{source_id}"
        if not source_id or key in seen:
            continue
        seen.add(key)

        # Check if person already exists by source_id in JSONB
        stmt = select(Person).where(
            Person.source_ids[source].astext == str(source_id)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            id_map[key] = existing.id
            # Update display_name if needed
            if p.get("display_name") and p["display_name"] != existing.display_name:
                existing.display_name = p["display_name"]
            if p.get("email") and not existing.email:
                existing.email = p["email"]
        else:
            # Also try matching by email
            if p.get("email"):
                stmt2 = select(Person).where(Person.email == p["email"])
                result2 = await session.execute(stmt2)
                existing_by_email = result2.scalar_one_or_none()
                if existing_by_email:
                    # Merge source_id into existing person
                    source_ids = dict(existing_by_email.source_ids or {})
                    source_ids[source] = source_id
                    existing_by_email.source_ids = source_ids
                    id_map[key] = existing_by_email.id
                    continue

            # Create new person
            new_person = Person(
                display_name=p.get("display_name", "Unknown"),
                email=p.get("email"),
                source_ids={source: source_id},
            )
            session.add(new_person)
            await session.flush()
            id_map[key] = new_person.id
            stats.persons_upserted += 1

    return id_map


async def _upsert_sprints(
    session: AsyncSession,
    sprints: list[dict[str, Any]],
    stats: NormalizeStats,
) -> dict[str, uuid.UUID]:
    """Upsert sprints, returns mapping of 'source:source_id' -> sprint UUID."""
    id_map: dict[str, uuid.UUID] = {}
    seen: set[str] = set()

    for sp in sprints:
        source = sp.get("source", "")
        source_id = sp.get("source_id", "")
        key = f"{source}:{source_id}"
        if not source_id or key in seen:
            continue
        seen.add(key)

        stmt = select(Sprint).where(Sprint.source == source, Sprint.source_id == source_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.name = sp.get("name", existing.name)
            existing.status = sp.get("status", existing.status)
            if sp.get("start_date"):
                existing.start_date = sp["start_date"]
            if sp.get("end_date"):
                existing.end_date = sp["end_date"]
            if sp.get("goal"):
                existing.goal = sp["goal"]
            if sp.get("extra"):
                existing.extra = {**(existing.extra or {}), **sp["extra"]}
            id_map[key] = existing.id
        else:
            new_sprint = Sprint(
                name=sp.get("name", ""),
                source=source,
                source_id=source_id,
                board_or_project=sp.get("board_or_project"),
                status=sp.get("status", "future"),
                start_date=sp.get("start_date"),
                end_date=sp.get("end_date"),
                goal=sp.get("goal"),
                extra=sp.get("extra"),
            )
            session.add(new_sprint)
            await session.flush()
            id_map[key] = new_sprint.id
            stats.sprints_upserted += 1

    return id_map


async def _upsert_work_items(
    session: AsyncSession,
    work_items: list[dict[str, Any]],
    person_id_map: dict[str, uuid.UUID],
    sprint_id_map: dict[str, uuid.UUID],
    stats: NormalizeStats,
) -> dict[str, uuid.UUID]:
    """Upsert work items, resolving FK references."""
    id_map: dict[str, uuid.UUID] = {}

    for wi in work_items:
        source = wi.get("source", "")
        source_id = wi.get("source_id", "")
        key = f"{source}:{source_id}"

        # Resolve assignee
        assignee_id = None
        if wi.get("assignee_source") and wi.get("assignee_source_id"):
            assignee_key = f"{wi['assignee_source']}:{wi['assignee_source_id']}"
            assignee_id = person_id_map.get(assignee_key)

        # Resolve sprint
        sprint_id = None
        if wi.get("sprint_source_id"):
            sprint_key = f"{source}:{wi['sprint_source_id']}"
            sprint_id = sprint_id_map.get(sprint_key)

        # Resolve parent
        parent_id = None
        if wi.get("parent_source_id"):
            parent_key = f"{source}:{wi['parent_source_id']}"
            parent_id = id_map.get(parent_key)
            if not parent_id:
                # Try to find in DB
                stmt = select(WorkItem.id).where(
                    WorkItem.source == source,
                    WorkItem.source_id == wi["parent_source_id"],
                )
                result = await session.execute(stmt)
                parent_id = result.scalar_one_or_none()

        # Check for existing
        stmt = select(WorkItem).where(WorkItem.source == source, WorkItem.source_id == source_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update fields
            existing.title = wi.get("title", existing.title)
            existing.description = wi.get("description", existing.description)
            existing.item_type = wi.get("item_type", existing.item_type)
            existing.status = wi.get("status", existing.status)
            existing.priority = wi.get("priority", existing.priority)
            existing.story_points = wi.get("story_points", existing.story_points)
            existing.due_date = wi.get("due_date", existing.due_date)
            existing.resolved_at = wi.get("resolved_at", existing.resolved_at)
            existing.labels = wi.get("labels", existing.labels)
            if assignee_id:
                existing.assignee_id = assignee_id
            if sprint_id:
                existing.sprint_id = sprint_id
            if parent_id:
                existing.parent_id = parent_id
            if wi.get("extra"):
                existing.extra = {**(existing.extra or {}), **wi["extra"]}
            # Append to changelog if status changed
            raw_changelog = wi.get("_raw_changelog")
            if raw_changelog:
                existing.changelog = list(existing.changelog or []) + (
                    raw_changelog if isinstance(raw_changelog, list) else [raw_changelog]
                )
            id_map[key] = existing.id
        else:
            new_item = WorkItem(
                source=source,
                source_id=source_id,
                title=wi.get("title", "Untitled"),
                description=wi.get("description"),
                item_type=wi.get("item_type", "task"),
                status=wi.get("status", "open"),
                priority=wi.get("priority"),
                story_points=wi.get("story_points"),
                due_date=wi.get("due_date"),
                resolved_at=wi.get("resolved_at"),
                assignee_id=assignee_id,
                sprint_id=sprint_id,
                parent_id=parent_id,
                labels=wi.get("labels", []),
                changelog=wi.get("_raw_changelog") or [],
                extra=wi.get("extra"),
            )
            session.add(new_item)
            await session.flush()
            id_map[key] = new_item.id
            stats.work_items_upserted += 1

    return id_map


async def _upsert_doc_entries(
    session: AsyncSession,
    doc_entries: list[dict[str, Any]],
    person_id_map: dict[str, uuid.UUID],
    stats: NormalizeStats,
) -> dict[str, uuid.UUID]:
    """Upsert doc entries, returns mapping of 'source:source_id' -> doc UUID."""
    id_map: dict[str, uuid.UUID] = {}

    for doc in doc_entries:
        source = doc.get("source", "")
        source_id = doc.get("source_id", "")
        key = f"{source}:{source_id}"

        # Resolve author
        author_id = None
        if doc.get("author_source") and doc.get("author_source_id"):
            author_key = f"{doc['author_source']}:{doc['author_source_id']}"
            author_id = person_id_map.get(author_key)

        stmt = select(DocEntry).where(DocEntry.source == source, DocEntry.source_id == source_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.title = doc.get("title", existing.title)
            existing.doc_type = doc.get("doc_type", existing.doc_type)
            existing.url = doc.get("url", existing.url)
            if doc.get("body_text"):
                existing.body_text = doc["body_text"]
            if author_id:
                existing.author_id = author_id
            existing.space_or_parent = doc.get("space_or_parent", existing.space_or_parent)
            existing.labels = doc.get("labels", existing.labels)
            if doc.get("extra"):
                existing.extra = {**(existing.extra or {}), **doc["extra"]}
            id_map[key] = existing.id
        else:
            new_doc = DocEntry(
                source=source,
                source_id=source_id,
                title=doc.get("title", "Untitled"),
                doc_type=doc.get("doc_type", "page"),
                url=doc.get("url"),
                body_text=doc.get("body_text"),
                author_id=author_id,
                space_or_parent=doc.get("space_or_parent"),
                labels=doc.get("labels", []),
                occurred_at=doc.get("occurred_at"),
                extra=doc.get("extra"),
            )
            session.add(new_doc)
            await session.flush()
            id_map[key] = new_doc.id
            stats.doc_entries_upserted += 1

    return id_map


async def _upsert_interactions(
    session: AsyncSession,
    interactions: list[dict[str, Any]],
    person_id_map: dict[str, uuid.UUID],
    work_item_id_map: dict[str, uuid.UUID],
    doc_id_map: dict[str, uuid.UUID],
    stats: NormalizeStats,
) -> dict[str, uuid.UUID]:
    """Upsert interaction events."""
    id_map: dict[str, uuid.UUID] = {}

    for ie in interactions:
        source = ie.get("source", "")
        source_id = ie.get("source_id", "")
        key = f"{source}:{source_id}"

        # Resolve author
        author_id = None
        if ie.get("author_source") and ie.get("author_source_id"):
            author_key = f"{ie['author_source']}:{ie['author_source_id']}"
            author_id = person_id_map.get(author_key)

        # Resolve work_item reference
        work_item_id = None
        if ie.get("work_item_source_id"):
            wi_key = f"{source}:{ie['work_item_source_id']}"
            work_item_id = work_item_id_map.get(wi_key)
            if not work_item_id:
                # Try DB lookup
                stmt = select(WorkItem.id).where(
                    WorkItem.source == source,
                    WorkItem.source_id == ie["work_item_source_id"],
                )
                result = await session.execute(stmt)
                work_item_id = result.scalar_one_or_none()

        # Resolve doc_entry reference
        doc_entry_id = None
        if ie.get("doc_entry_source_id"):
            doc_key = f"{source}:{ie['doc_entry_source_id']}"
            doc_entry_id = doc_id_map.get(doc_key)

        # Resolve parent interaction
        parent_interaction_id = None
        if ie.get("parent_source_id"):
            parent_key = f"{source}:{ie['parent_source_id']}"
            parent_interaction_id = id_map.get(parent_key)
            if not parent_interaction_id:
                stmt = select(InteractionEvent.id).where(
                    InteractionEvent.source == source,
                    InteractionEvent.source_id == ie["parent_source_id"],
                )
                result = await session.execute(stmt)
                parent_interaction_id = result.scalar_one_or_none()

        stmt = select(InteractionEvent).where(
            InteractionEvent.source == source,
            InteractionEvent.source_id == source_id,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.event_type = ie.get("event_type", existing.event_type)
            existing.channel_or_context = ie.get("channel_or_context", existing.channel_or_context)
            if author_id:
                existing.author_id = author_id
            existing.body = ie.get("body", existing.body)
            if work_item_id:
                existing.work_item_id = work_item_id
            if doc_entry_id:
                existing.doc_entry_id = doc_entry_id
            if parent_interaction_id:
                existing.parent_interaction_id = parent_interaction_id
            if ie.get("extra"):
                existing.extra = {**(existing.extra or {}), **ie["extra"]}
            id_map[key] = existing.id
        else:
            new_ie = InteractionEvent(
                source=source,
                source_id=source_id,
                event_type=ie.get("event_type", "message"),
                channel_or_context=ie.get("channel_or_context"),
                author_id=author_id,
                body=ie.get("body"),
                work_item_id=work_item_id,
                doc_entry_id=doc_entry_id,
                parent_interaction_id=parent_interaction_id,
                occurred_at=ie.get("occurred_at"),
                extra=ie.get("extra"),
            )
            session.add(new_ie)
            await session.flush()
            id_map[key] = new_ie.id
            stats.interactions_upserted += 1

    return id_map


# ── CLI entry point ───────────────────────────────────────────────────


async def validate_only() -> ValidationReport:
    """Run validation without processing any events."""
    async with async_session() as session:
        return await validate_post_normalize(session)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize raw_events into canonical tables."
    )
    parser.add_argument(
        "--since",
        required=True,
        help="Process events from this timestamp (ISO 8601).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run mappers but do not commit changes.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only run validation checks, skip normalization.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of raw_events per batch (default: 500).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.validate_only:
        report = asyncio.run(validate_only())
        print("\n=== Validation Report ===")
        for k, v in report.summary().items():
            print(f"  {k}: {v}")
        sys.exit(0 if report.ok else 1)

    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    logger.info("Starting normalization since=%s dry_run=%s", since, args.dry_run)
    stats, report = asyncio.run(
        normalize(since=since, dry_run=args.dry_run, batch_size=args.batch_size)
    )

    print("\n=== Normalization Stats ===")
    for k, v in stats.summary().items():
        print(f"  {k}: {v}")

    if report:
        print("\n=== Validation Report ===")
        for k, v in report.summary().items():
            print(f"  {k}: {v}")
        if not report.ok:
            sys.exit(1)


if __name__ == "__main__":
    main()

"""Validation layer for the normalization pipeline.

Ensures no duplicates, foreign key integrity, required fields present,
and metrics extraction fields are ready.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doc_entry import DocEntry
from app.models.external_link import ExternalLink
from app.models.interaction_event import InteractionEvent
from app.models.person import Person
from app.models.sprint import Sprint
from app.models.work_item import WorkItem

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Summary of validation checks."""

    total_checks: int = 0
    passed: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_pass(self, msg: str) -> None:
        self.total_checks += 1
        self.passed += 1
        logger.debug("PASS: %s", msg)

    def add_warning(self, msg: str) -> None:
        self.total_checks += 1
        self.warnings.append(msg)
        logger.warning("WARN: %s", msg)

    def add_error(self, msg: str) -> None:
        self.total_checks += 1
        self.errors.append(msg)
        logger.error("FAIL: %s", msg)

    def summary(self) -> dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "passed": self.passed,
            "warnings": len(self.warnings),
            "errors": len(self.errors),
            "ok": self.ok,
            "error_details": self.errors,
            "warning_details": self.warnings,
        }


async def validate_post_normalize(session: AsyncSession) -> ValidationReport:
    """Run all validation checks after normalization. Returns a ValidationReport."""
    report = ValidationReport()

    await _check_work_item_duplicates(session, report)
    await _check_sprint_duplicates(session, report)
    await _check_doc_duplicates(session, report)
    await _check_interaction_duplicates(session, report)
    await _check_work_item_fk_assignee(session, report)
    await _check_work_item_fk_sprint(session, report)
    await _check_work_item_fk_parent(session, report)
    await _check_interaction_fk_author(session, report)
    await _check_interaction_fk_work_item(session, report)
    await _check_external_link_integrity(session, report)
    await _check_metrics_readiness(session, report)

    return report


# ── duplicate checks ──────────────────────────────────────────────────


async def _check_work_item_duplicates(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(WorkItem.source, WorkItem.source_id, func.count().label("cnt"))
        .group_by(WorkItem.source, WorkItem.source_id)
        .having(func.count() > 1)
    )
    result = await session.execute(stmt)
    dupes = result.all()
    if dupes:
        for row in dupes:
            report.add_error(f"Duplicate work_item: {row[0]}/{row[1]} (count={row[2]})")
    else:
        report.add_pass("No duplicate work_items")


async def _check_sprint_duplicates(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(Sprint.source, Sprint.source_id, func.count().label("cnt"))
        .group_by(Sprint.source, Sprint.source_id)
        .having(func.count() > 1)
    )
    result = await session.execute(stmt)
    dupes = result.all()
    if dupes:
        for row in dupes:
            report.add_error(f"Duplicate sprint: {row[0]}/{row[1]} (count={row[2]})")
    else:
        report.add_pass("No duplicate sprints")


async def _check_doc_duplicates(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(DocEntry.source, DocEntry.source_id, func.count().label("cnt"))
        .group_by(DocEntry.source, DocEntry.source_id)
        .having(func.count() > 1)
    )
    result = await session.execute(stmt)
    dupes = result.all()
    if dupes:
        for row in dupes:
            report.add_error(f"Duplicate doc_entry: {row[0]}/{row[1]} (count={row[2]})")
    else:
        report.add_pass("No duplicate doc_entries")


async def _check_interaction_duplicates(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(InteractionEvent.source, InteractionEvent.source_id, func.count().label("cnt"))
        .group_by(InteractionEvent.source, InteractionEvent.source_id)
        .having(func.count() > 1)
    )
    result = await session.execute(stmt)
    dupes = result.all()
    if dupes:
        for row in dupes:
            report.add_error(f"Duplicate interaction_event: {row[0]}/{row[1]} (count={row[2]})")
    else:
        report.add_pass("No duplicate interaction_events")


# ── foreign key integrity ─────────────────────────────────────────────


async def _check_work_item_fk_assignee(session: AsyncSession, report: ValidationReport) -> None:
    """Check that all work_item.assignee_id references exist in person."""
    stmt = (
        select(func.count())
        .select_from(WorkItem)
        .where(
            WorkItem.assignee_id.is_not(None),
            ~WorkItem.assignee_id.in_(select(Person.id)),
        )
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    if count > 0:
        report.add_error(f"{count} work_items have assignee_id not found in person table")
    else:
        report.add_pass("All work_item assignee_ids are valid")


async def _check_work_item_fk_sprint(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(func.count())
        .select_from(WorkItem)
        .where(
            WorkItem.sprint_id.is_not(None),
            ~WorkItem.sprint_id.in_(select(Sprint.id)),
        )
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    if count > 0:
        report.add_error(f"{count} work_items have sprint_id not found in sprint table")
    else:
        report.add_pass("All work_item sprint_ids are valid")


async def _check_work_item_fk_parent(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(func.count())
        .select_from(WorkItem)
        .where(
            WorkItem.parent_id.is_not(None),
            ~WorkItem.parent_id.in_(select(WorkItem.id)),
        )
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    if count > 0:
        report.add_warning(f"{count} work_items have parent_id not found (parent may not be ingested yet)")
    else:
        report.add_pass("All work_item parent_ids are valid")


async def _check_interaction_fk_author(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(func.count())
        .select_from(InteractionEvent)
        .where(
            InteractionEvent.author_id.is_not(None),
            ~InteractionEvent.author_id.in_(select(Person.id)),
        )
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    if count > 0:
        report.add_error(f"{count} interaction_events have author_id not found in person table")
    else:
        report.add_pass("All interaction_event author_ids are valid")


async def _check_interaction_fk_work_item(session: AsyncSession, report: ValidationReport) -> None:
    stmt = (
        select(func.count())
        .select_from(InteractionEvent)
        .where(
            InteractionEvent.work_item_id.is_not(None),
            ~InteractionEvent.work_item_id.in_(select(WorkItem.id)),
        )
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    if count > 0:
        report.add_warning(
            f"{count} interaction_events have work_item_id not found "
            "(work item may not be ingested yet)"
        )
    else:
        report.add_pass("All interaction_event work_item_ids are valid")


# ── external link integrity ───────────────────────────────────────────


async def _check_external_link_integrity(session: AsyncSession, report: ValidationReport) -> None:
    """Check that external_link canonical_ids actually exist in their target tables."""
    table_model_map = {
        "work_item": WorkItem,
        "sprint": Sprint,
        "person": Person,
        "doc_entry": DocEntry,
    }
    for table_name, model in table_model_map.items():
        stmt = (
            select(func.count())
            .select_from(ExternalLink)
            .where(
                ExternalLink.canonical_table == table_name,
                ~ExternalLink.canonical_id.in_(select(model.id)),
            )
        )
        result = await session.execute(stmt)
        count = result.scalar_one()
        if count > 0:
            report.add_warning(
                f"{count} external_links for {table_name} point to non-existent IDs"
            )
        else:
            report.add_pass(f"All external_links for {table_name} are valid")


# ── metrics readiness ─────────────────────────────────────────────────


async def _check_metrics_readiness(session: AsyncSession, report: ValidationReport) -> None:
    """Verify that key fields for analytics are populated."""
    # Check work items have status
    stmt = select(func.count()).select_from(WorkItem).where(WorkItem.status.is_(None))
    result = await session.execute(stmt)
    null_status = result.scalar_one()
    if null_status > 0:
        report.add_error(f"{null_status} work_items have NULL status")
    else:
        report.add_pass("All work_items have a status")

    # Check story_points coverage (warning, not error)
    total_stmt = select(func.count()).select_from(WorkItem)
    total_result = await session.execute(total_stmt)
    total = total_result.scalar_one()

    if total > 0:
        with_points_stmt = (
            select(func.count()).select_from(WorkItem).where(WorkItem.story_points.is_not(None))
        )
        with_points_result = await session.execute(with_points_stmt)
        with_points = with_points_result.scalar_one()
        pct = (with_points / total) * 100
        if pct < 50:
            report.add_warning(
                f"Only {pct:.0f}% of work_items have story_points ({with_points}/{total})"
            )
        else:
            report.add_pass(f"{pct:.0f}% of work_items have story_points")

    # Check sprint assignment coverage
    if total > 0:
        with_sprint_stmt = (
            select(func.count()).select_from(WorkItem).where(WorkItem.sprint_id.is_not(None))
        )
        with_sprint_result = await session.execute(with_sprint_stmt)
        with_sprint = with_sprint_result.scalar_one()
        pct = (with_sprint / total) * 100
        if pct < 30:
            report.add_warning(
                f"Only {pct:.0f}% of work_items have sprint_id ({with_sprint}/{total})"
            )
        else:
            report.add_pass(f"{pct:.0f}% of work_items have sprint_id")

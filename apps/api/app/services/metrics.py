"""Agile metrics computation — pure functions over canonical tables.

All public functions accept plain lists / dicts so they are testable
without a database.  The ``MetricsService`` class orchestrates DB
access and delegates to these functions.

Changelog convention (work_item.changelog JSONB array):
  [{"field": "status", "from": "open", "to": "in_progress",
    "at": "2025-01-10T10:00:00Z"}, ...]
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metric_snapshot import MetricSnapshotDaily, SprintBurndownPoint
from app.models.sprint import Sprint
from app.models.work_item import WorkItem

# ── Status buckets (configurable via caller) ──────────────────────
DEFAULT_STATUS_BUCKETS: dict[str, list[str]] = {
    "todo": ["open"],
    "in_progress": ["in_progress", "review"],
    "done": ["done", "closed"],
}

DONE_STATUSES = {"done", "closed"}


# ── Helpers ───────────────────────────────────────────────────────

def _parse_dt(val: str | datetime | None) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _date_range(start: date, end: date) -> list[date]:
    """Inclusive date range."""
    days: list[date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def _item_story_points(item: WorkItem | dict) -> float:
    if isinstance(item, dict):
        return float(item.get("story_points") or 0)
    return float(item.story_points or 0)


def _item_status(item: WorkItem | dict) -> str:
    if isinstance(item, dict):
        return item.get("status", "open")
    return item.status or "open"


def _item_changelog(item: WorkItem | dict) -> list[dict]:
    if isinstance(item, dict):
        return item.get("changelog") or []
    return item.changelog or []


def _item_created_at(item: WorkItem | dict) -> datetime | None:
    if isinstance(item, dict):
        return _parse_dt(item.get("created_at"))
    return item.created_at


def _item_resolved_at(item: WorkItem | dict) -> datetime | None:
    if isinstance(item, dict):
        return _parse_dt(item.get("resolved_at"))
    return item.resolved_at


def _item_due_date(item: WorkItem | dict) -> date | None:
    if isinstance(item, dict):
        val = item.get("due_date")
        if isinstance(val, str):
            return date.fromisoformat(val)
        return val
    return item.due_date


def _item_labels(item: WorkItem | dict) -> list[str]:
    if isinstance(item, dict):
        return item.get("labels") or []
    return item.labels or []


def _item_title(item: WorkItem | dict) -> str:
    if isinstance(item, dict):
        return item.get("title", "")
    return item.title or ""


def _item_source_id(item: WorkItem | dict) -> str:
    if isinstance(item, dict):
        return item.get("source_id", "")
    return item.source_id or ""


# ── Sprint: Burndown ─────────────────────────────────────────────

def compute_burndown(
    items: Sequence[WorkItem | dict],
    sprint_start: date,
    sprint_end: date,
) -> list[dict[str, Any]]:
    """Compute daily burndown series for a sprint.

    Returns list of ``{"date": "YYYY-MM-DD", "remaining": float, "completed": float}``.
    Uses changelog status transitions to determine *when* each item was completed.
    """
    total_points = sum(_item_story_points(i) for i in items)

    # Build a map: date → points completed on that date
    completed_on: dict[date, float] = defaultdict(float)
    for item in items:
        pts = _item_story_points(item)
        if pts == 0:
            continue
        done_date = _completion_date(item)
        if done_date:
            completed_on[done_date] += pts

    days = _date_range(sprint_start, sprint_end)
    series: list[dict[str, Any]] = []
    cumulative_done = 0.0
    for d in days:
        cumulative_done += completed_on.get(d, 0.0)
        series.append({
            "date": d.isoformat(),
            "remaining": round(total_points - cumulative_done, 2),
            "completed": round(cumulative_done, 2),
        })
    return series


def _completion_date(item: WorkItem | dict) -> date | None:
    """Extract the date when an item transitioned to a done status."""
    changelog = _item_changelog(item)
    for entry in changelog:
        if entry.get("field") == "status" and entry.get("to") in DONE_STATUSES:
            dt = _parse_dt(entry.get("at"))
            if dt:
                return dt.date()
    # Fallback: resolved_at
    resolved = _item_resolved_at(item)
    if resolved and _item_status(item) in DONE_STATUSES:
        return resolved.date()
    return None


# ── Sprint: Velocity ─────────────────────────────────────────────

def compute_velocity(
    sprints_with_items: Sequence[tuple[Sprint | dict, Sequence[WorkItem | dict]]],
) -> list[dict[str, Any]]:
    """Velocity per sprint: committed vs completed story points.

    Returns list of ``{"sprint_name": str, "committed": float, "completed": float}``.
    """
    result: list[dict[str, Any]] = []
    for sprint, items in sprints_with_items:
        sprint_name = sprint["name"] if isinstance(sprint, dict) else sprint.name
        committed = sum(_item_story_points(i) for i in items)
        completed = sum(
            _item_story_points(i) for i in items
            if _item_status(i) in DONE_STATUSES
        )
        result.append({
            "sprint_name": sprint_name,
            "committed": round(committed, 2),
            "completed": round(completed, 2),
        })
    return result


# ── Sprint: Scope change ────────────────────────────────────────

def compute_scope_change(
    items: Sequence[WorkItem | dict],
    sprint_start: date,
) -> dict[str, Any]:
    """Detect items added or removed mid-sprint.

    An item is considered *added mid-sprint* if:
      - its created_at is after sprint_start, OR
      - its changelog shows a sprint field change *to* this sprint after start.

    An item is considered *removed* if:
      - its changelog shows a sprint field change *from* this sprint.

    Returns ``{"added": int, "removed": int, "added_points": float,
               "removed_points": float, "net_points": float}``.
    """
    added = 0
    removed = 0
    added_pts = 0.0
    removed_pts = 0.0

    for item in items:
        pts = _item_story_points(item)
        created = _item_created_at(item)
        if created and created.date() > sprint_start:
            added += 1
            added_pts += pts
            continue

        changelog = _item_changelog(item)
        for entry in changelog:
            if entry.get("field") == "sprint":
                change_dt = _parse_dt(entry.get("at"))
                if change_dt and change_dt.date() > sprint_start:
                    if entry.get("from") is not None and entry.get("to") is not None:
                        # moved between sprints: counts as added to current
                        added += 1
                        added_pts += pts
                    elif entry.get("to") is None:
                        removed += 1
                        removed_pts += pts
                    break

    return {
        "added": added,
        "removed": removed,
        "added_points": round(added_pts, 2),
        "removed_points": round(removed_pts, 2),
        "net_points": round(added_pts - removed_pts, 2),
    }


# ── Sprint: Report (done vs not-done) ────────────────────────────

def compute_sprint_report(
    items: Sequence[WorkItem | dict],
) -> dict[str, list[dict[str, Any]]]:
    """Split sprint items into done vs not-done lists.

    Returns ``{"done": [...], "not_done": [...]}``.
    """
    done: list[dict[str, Any]] = []
    not_done: list[dict[str, Any]] = []
    for item in items:
        entry = {
            "source_id": _item_source_id(item),
            "title": _item_title(item),
            "story_points": _item_story_points(item),
            "status": _item_status(item),
        }
        if _item_status(item) in DONE_STATUSES:
            done.append(entry)
        else:
            not_done.append(entry)
    return {"done": done, "not_done": not_done}


# ── Flow: Cumulative Flow Diagram ────────────────────────────────

def compute_cumulative_flow(
    items: Sequence[WorkItem | dict],
    start: date,
    end: date,
    status_buckets: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Cumulative flow diagram: WIP by status bucket for each day.

    Returns list of ``{"date": "YYYY-MM-DD", "todo": int, "in_progress": int, "done": int}``.
    """
    buckets = status_buckets or DEFAULT_STATUS_BUCKETS
    bucket_names = list(buckets.keys())
    status_to_bucket: dict[str, str] = {}
    for bucket, statuses in buckets.items():
        for s in statuses:
            status_to_bucket[s] = bucket

    # For each item, build a timeline of status changes
    item_timelines: list[list[tuple[date, str]]] = []
    for item in items:
        timeline: list[tuple[date, str]] = []
        created = _item_created_at(item)
        if created:
            timeline.append((created.date(), status_to_bucket.get("open", bucket_names[0])))

        for entry in _item_changelog(item):
            if entry.get("field") == "status":
                dt = _parse_dt(entry.get("at"))
                to_status = entry.get("to", "open")
                if dt:
                    timeline.append((dt.date(), status_to_bucket.get(to_status, bucket_names[0])))

        timeline.sort(key=lambda t: t[0])
        item_timelines.append(timeline)

    days = _date_range(start, end)
    series: list[dict[str, Any]] = []
    for d in days:
        counts: dict[str, int] = {b: 0 for b in bucket_names}
        for timeline in item_timelines:
            if not timeline:
                continue
            # Find the latest status on or before day d
            current_bucket: str | None = None
            for change_date, bucket in timeline:
                if change_date <= d:
                    current_bucket = bucket
                else:
                    break
            if current_bucket:
                counts[current_bucket] += 1
        row: dict[str, Any] = {"date": d.isoformat()}
        row.update(counts)
        series.append(row)
    return series


# ── Flow: Lead time / Cycle time ─────────────────────────────────

def compute_lead_cycle_times(
    items: Sequence[WorkItem | dict],
) -> dict[str, Any]:
    """Compute median lead time and cycle time (in calendar days) for resolved items.

    * Lead time = resolved_at - created_at
    * Cycle time = resolved_at - first transition to in_progress/review
    """
    lead_times: list[float] = []
    cycle_times: list[float] = []

    for item in items:
        resolved = _item_resolved_at(item)
        created = _item_created_at(item)
        if not resolved:
            continue

        if created:
            lead_days = (resolved - created).total_seconds() / 86400
            lead_times.append(lead_days)

        # Find first in_progress transition
        first_active: datetime | None = None
        for entry in _item_changelog(item):
            if entry.get("field") == "status" and entry.get("to") in ("in_progress", "review"):
                dt = _parse_dt(entry.get("at"))
                if dt and (first_active is None or dt < first_active):
                    first_active = dt

        if first_active:
            cycle_days = (resolved - first_active).total_seconds() / 86400
            cycle_times.append(cycle_days)

    return {
        "lead_time_median_days": round(statistics.median(lead_times), 2) if lead_times else None,
        "lead_time_count": len(lead_times),
        "cycle_time_median_days": round(statistics.median(cycle_times), 2) if cycle_times else None,
        "cycle_time_count": len(cycle_times),
    }


# ── Flow: Throughput ─────────────────────────────────────────────

def compute_throughput(
    items: Sequence[WorkItem | dict],
    start: date,
    end: date,
) -> dict[str, Any]:
    """Count of items completed per day and per week in the given range.

    Returns ``{"daily": [{"date": ..., "count": int}], "weekly": [{"week": ..., "count": int}],
               "total": int}``.
    """
    daily: dict[date, int] = defaultdict(int)
    for item in items:
        done_date = _completion_date(item)
        if done_date and start <= done_date <= end:
            daily[done_date] += 1

    daily_series = [
        {"date": d.isoformat(), "count": daily.get(d, 0)}
        for d in _date_range(start, end)
    ]

    weekly: dict[str, int] = defaultdict(int)
    for d, count in daily.items():
        # ISO week label
        iso = d.isocalendar()
        week_label = f"{iso.year}-W{iso.week:02d}"
        weekly[week_label] += count

    weekly_series = [{"week": w, "count": c} for w, c in sorted(weekly.items())]
    total = sum(daily.values())

    return {"daily": daily_series, "weekly": weekly_series, "total": total}


# ── Due-date risk ────────────────────────────────────────────────

def compute_due_date_risk(
    items: Sequence[WorkItem | dict],
    as_of: date | None = None,
) -> dict[str, Any]:
    """Classify open items by due-date risk.

    Returns ``{"overdue": [...], "due_7d": [...], "due_14d": [...], "no_due_date": [...],
               "by_label": {label: {"overdue": int, "due_7d": int, "due_14d": int}}}``.
    """
    ref = as_of or date.today()
    overdue: list[dict] = []
    due_7d: list[dict] = []
    due_14d: list[dict] = []
    no_due: list[dict] = []
    label_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"overdue": 0, "due_7d": 0, "due_14d": 0})

    for item in items:
        if _item_status(item) in DONE_STATUSES:
            continue
        due = _item_due_date(item)
        entry = {
            "source_id": _item_source_id(item),
            "title": _item_title(item),
            "due_date": due.isoformat() if due else None,
            "status": _item_status(item),
            "labels": _item_labels(item),
        }
        if due is None:
            no_due.append(entry)
            continue

        diff = (due - ref).days
        bucket: str | None = None
        if diff < 0:
            overdue.append(entry)
            bucket = "overdue"
        elif diff <= 7:
            due_7d.append(entry)
            bucket = "due_7d"
        elif diff <= 14:
            due_14d.append(entry)
            bucket = "due_14d"

        if bucket:
            for label in _item_labels(item):
                label_counts[label][bucket] += 1

    return {
        "overdue": overdue,
        "due_7d": due_7d,
        "due_14d": due_14d,
        "no_due_date": no_due,
        "by_label": dict(label_counts),
    }


# ══════════════════════════════════════════════════════════════════
# Service class — orchestrates DB access + computation
# ══════════════════════════════════════════════════════════════════

class MetricsService:
    """Stateless service: receives a session per call."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Sprint metrics ────────────────────────────────────────────

    async def get_sprint_metrics(self, sprint_id: uuid.UUID) -> dict[str, Any]:
        """Full sprint dashboard: burndown, velocity, scope change, report."""
        sprint = await self.session.get(Sprint, sprint_id)
        if not sprint:
            return {}

        stmt = select(WorkItem).where(WorkItem.sprint_id == sprint_id)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        start = sprint.start_date or date.today()
        end = sprint.end_date or date.today()

        burndown = compute_burndown(items, start, end)
        scope = compute_scope_change(items, start)
        report = compute_sprint_report(items)
        velocity = compute_velocity([(sprint, items)])
        flow = compute_cumulative_flow(items, start, end)
        lead_cycle = compute_lead_cycle_times(items)
        throughput = compute_throughput(items, start, end)

        return {
            "sprint": {
                "id": str(sprint.id),
                "name": sprint.name,
                "status": sprint.status,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            "burndown": burndown,
            "velocity": velocity[0] if velocity else {},
            "scope_change": scope,
            "report": report,
            "cumulative_flow": flow,
            "lead_cycle_time": lead_cycle,
            "throughput": throughput,
        }

    # ── Team metrics ──────────────────────────────────────────────

    async def get_team_metrics(
        self,
        team_id: str,
        from_date: date,
        to_date: date,
    ) -> dict[str, Any]:
        """Team dashboard: velocity history, flow, lead/cycle time, throughput, due-date risk."""
        from app.models.person import Person

        # Get team members
        person_stmt = select(Person.id).where(Person.team == team_id)
        person_result = await self.session.execute(person_stmt)
        person_ids = [row[0] for row in person_result.all()]

        # Get work items assigned to team in date range
        item_stmt = select(WorkItem).where(
            WorkItem.assignee_id.in_(person_ids),
            WorkItem.created_at >= datetime.combine(from_date, datetime.min.time()),
        )
        result = await self.session.execute(item_stmt)
        items = list(result.scalars().all())

        # Get sprints that overlap the date range
        sprint_stmt = select(Sprint).where(
            Sprint.start_date <= to_date,
            Sprint.end_date >= from_date,
        )
        sprint_result = await self.session.execute(sprint_stmt)
        sprints = list(sprint_result.scalars().all())

        # Velocity: gather items per sprint
        sprint_items: list[tuple[Sprint, list[WorkItem]]] = []
        for sprint in sprints:
            si_stmt = select(WorkItem).where(WorkItem.sprint_id == sprint.id)
            si_result = await self.session.execute(si_stmt)
            si = list(si_result.scalars().all())
            # Filter to team members
            si = [i for i in si if i.assignee_id in person_ids]
            sprint_items.append((sprint, si))

        velocity = compute_velocity(sprint_items)
        flow = compute_cumulative_flow(items, from_date, to_date)
        lead_cycle = compute_lead_cycle_times(items)
        throughput = compute_throughput(items, from_date, to_date)
        due_risk = compute_due_date_risk(items)

        return {
            "team_id": team_id,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "velocity": velocity,
            "cumulative_flow": flow,
            "lead_cycle_time": lead_cycle,
            "throughput": throughput,
            "due_date_risk": due_risk,
        }

    # ── Snapshot materialisation ──────────────────────────────────

    async def materialise_daily_snapshot(
        self,
        snapshot_date: date,
        team_id: str | None,
        sprint_id: uuid.UUID | None,
        metrics_json: dict,
    ) -> MetricSnapshotDaily:
        """Upsert a daily metrics snapshot."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = {
            "date": snapshot_date,
            "team_id": team_id,
            "sprint_id": sprint_id,
            "metrics_json": metrics_json,
        }
        stmt = pg_insert(MetricSnapshotDaily).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "team_id", "sprint_id"],
            set_={"metrics_json": metrics_json},
        )
        await self.session.execute(stmt)
        await self.session.commit()

        result = await self.session.execute(
            select(MetricSnapshotDaily).where(
                MetricSnapshotDaily.date == snapshot_date,
                MetricSnapshotDaily.team_id == team_id,
                MetricSnapshotDaily.sprint_id == sprint_id,
            )
        )
        return result.scalar_one()

    async def materialise_burndown_point(
        self,
        snapshot_date: date,
        sprint_id: uuid.UUID,
        remaining: float,
        completed: float,
    ) -> SprintBurndownPoint:
        """Upsert a burndown data point."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = {
            "date": snapshot_date,
            "sprint_id": sprint_id,
            "remaining": remaining,
            "completed": completed,
        }
        stmt = pg_insert(SprintBurndownPoint).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["sprint_id", "date"],
            set_={"remaining": remaining, "completed": completed},
        )
        await self.session.execute(stmt)
        await self.session.commit()

        result = await self.session.execute(
            select(SprintBurndownPoint).where(
                SprintBurndownPoint.date == snapshot_date,
                SprintBurndownPoint.sprint_id == sprint_id,
            )
        )
        return result.scalar_one()

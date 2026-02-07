"""Seed script – populates the DB with realistic demo data.

Usage:
    cd apps/api
    python -m scripts.seed          # uses DATABASE_URL from .env / config
"""

import asyncio
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.effort_log import EffortLog
from app.models.person import Person
from app.models.raw_event import RawEvent
from app.models.report import Report
from app.models.sprint import Sprint
from app.models.work_item import WorkItem

# ── deterministic UUIDs so the script is re-runnable ────────────────
NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# ── people ──────────────────────────────────────────────────────────
PEOPLE = [
    Person(
        id=_uuid("alice"), display_name="Alice Chen", email="alice@example.com",
        role="admin", team="backend",
        source_ids={"jira": "alice-jira-001", "gitlab": 101},
    ),
    Person(
        id=_uuid("bob"), display_name="Bob Marley", email="bob@example.com",
        role="member", team="backend",
        source_ids={"jira": "bob-jira-002", "gitlab": 102},
    ),
    Person(
        id=_uuid("carol"), display_name="Carol Danvers", email="carol@example.com",
        role="member", team="frontend",
        source_ids={"jira": "carol-jira-003", "gitlab": 103},
    ),
    Person(
        id=_uuid("dave"), display_name="Dave Kim", email="dave@example.com",
        role="manager", team="frontend",
        source_ids={"jira": "dave-jira-004", "gitlab": 104},
    ),
]

# ── sprints ─────────────────────────────────────────────────────────
today = date.today()
sprint_start = today - timedelta(days=today.weekday())  # Monday of this week

SPRINTS = [
    Sprint(
        id=_uuid("sprint-23"), name="Sprint 23", source="jira", source_id="sprint-23",
        board_or_project="CASE", status="closed",
        start_date=sprint_start - timedelta(weeks=2),
        end_date=sprint_start - timedelta(days=1),
        goal="Finish ingestion pipeline v1",
    ),
    Sprint(
        id=_uuid("sprint-24"), name="Sprint 24", source="jira", source_id="sprint-24",
        board_or_project="CASE", status="active",
        start_date=sprint_start,
        end_date=sprint_start + timedelta(days=13),
        goal="CEO dashboard + report generation",
    ),
    Sprint(
        id=_uuid("sprint-25"), name="Sprint 25", source="jira", source_id="sprint-25",
        board_or_project="CASE", status="future",
        start_date=sprint_start + timedelta(weeks=2),
        end_date=sprint_start + timedelta(weeks=4, days=-1),
        goal="Alerting & notifications",
    ),
]

# ── work items ──────────────────────────────────────────────────────
ITEMS = [
    # Sprint 23 – closed items
    WorkItem(
        id=_uuid("CASE-101"), source="jira", source_id="CASE-101",
        title="Set up raw_event ingestion from Jira webhooks",
        item_type="story", status="done", priority="high", story_points=5,
        assignee_id=_uuid("alice"), sprint_id=_uuid("sprint-23"),
        due_date=sprint_start - timedelta(days=3),
        resolved_at=datetime(2025, 2, 3, 14, 30, tzinfo=timezone.utc),
        labels=["ingestion", "jira"],
        changelog=[
            {"from": "open", "to": "in_progress", "at": "2025-01-22T09:00:00Z"},
            {"from": "in_progress", "to": "review", "at": "2025-01-29T16:00:00Z"},
            {"from": "review", "to": "done", "at": "2025-02-03T14:30:00Z"},
        ],
    ),
    WorkItem(
        id=_uuid("CASE-102"), source="jira", source_id="CASE-102",
        title="GitLab MR webhook normalizer",
        item_type="story", status="done", priority="high", story_points=3,
        assignee_id=_uuid("bob"), sprint_id=_uuid("sprint-23"),
        due_date=sprint_start - timedelta(days=5),
        resolved_at=datetime(2025, 2, 1, 11, 0, tzinfo=timezone.utc),
        labels=["ingestion", "gitlab"],
        changelog=[
            {"from": "open", "to": "in_progress", "at": "2025-01-23T10:00:00Z"},
            {"from": "in_progress", "to": "done", "at": "2025-02-01T11:00:00Z"},
        ],
    ),
    WorkItem(
        id=_uuid("CASE-103"), source="jira", source_id="CASE-103",
        title="Idempotent hash deduplication for raw_event",
        item_type="task", status="done", priority="medium", story_points=2,
        assignee_id=_uuid("alice"), sprint_id=_uuid("sprint-23"),
        due_date=sprint_start - timedelta(days=2),
        resolved_at=datetime(2025, 2, 4, 17, 0, tzinfo=timezone.utc),
        labels=["ingestion"],
        changelog=[
            {"from": "open", "to": "in_progress", "at": "2025-01-30T08:00:00Z"},
            {"from": "in_progress", "to": "done", "at": "2025-02-04T17:00:00Z"},
        ],
    ),
    # Sprint 24 – active items
    WorkItem(
        id=_uuid("CASE-110"), source="jira", source_id="CASE-110",
        title="Build CEO daily brief report generator",
        item_type="story", status="in_progress", priority="critical", story_points=8,
        assignee_id=_uuid("alice"), sprint_id=_uuid("sprint-24"),
        due_date=sprint_start + timedelta(days=10),
        labels=["report", "ceo-dashboard"],
        changelog=[
            {"from": "open", "to": "in_progress", "at": str(sprint_start)},
        ],
    ),
    WorkItem(
        id=_uuid("CASE-111"), source="jira", source_id="CASE-111",
        title="Frontend: sprint burndown chart component",
        item_type="story", status="in_progress", priority="high", story_points=5,
        assignee_id=_uuid("carol"), sprint_id=_uuid("sprint-24"),
        due_date=sprint_start + timedelta(days=8),
        labels=["frontend", "charts"],
        changelog=[
            {"from": "open", "to": "in_progress", "at": str(sprint_start + timedelta(days=1))},
        ],
    ),
    WorkItem(
        id=_uuid("CASE-112"), source="jira", source_id="CASE-112",
        title="Effort log CRUD API endpoints",
        item_type="task", status="open", priority="medium", story_points=3,
        assignee_id=_uuid("bob"), sprint_id=_uuid("sprint-24"),
        due_date=sprint_start + timedelta(days=12),
        labels=["api", "effort"],
    ),
    WorkItem(
        id=_uuid("CASE-113"), source="gitlab", source_id="case-data#47",
        title="Fix N+1 query in work_item list endpoint",
        item_type="bug", status="open", priority="high", story_points=2,
        assignee_id=_uuid("bob"), sprint_id=_uuid("sprint-24"),
        due_date=sprint_start + timedelta(days=6),
        labels=["bug", "performance"],
    ),
    WorkItem(
        id=_uuid("CASE-114"), source="jira", source_id="CASE-114",
        title="Design weekly metrics email template",
        item_type="task", status="review", priority="medium", story_points=2,
        assignee_id=_uuid("dave"), sprint_id=_uuid("sprint-24"),
        due_date=sprint_start + timedelta(days=9),
        labels=["report", "design"],
        changelog=[
            {"from": "open", "to": "in_progress", "at": str(sprint_start + timedelta(days=2))},
            {"from": "in_progress", "to": "review", "at": str(sprint_start + timedelta(days=5))},
        ],
    ),
]

# ── effort logs ─────────────────────────────────────────────────────
EFFORT_LOGS: list[EffortLog] = []
_categories = ["development", "review", "meeting", "support"]
for day_offset in range(5):  # Mon-Fri of current sprint
    d = sprint_start + timedelta(days=day_offset)
    if d > today:
        break
    for person_name, hours_base in [("alice", 7), ("bob", 6.5), ("carol", 7), ("dave", 5)]:
        for cat_idx, hours in enumerate([hours_base - 2, 1, 0.5, 0.5]):
            if hours <= 0:
                continue
            EFFORT_LOGS.append(
                EffortLog(
                    id=_uuid(f"effort-{person_name}-{d}-{cat_idx}"),
                    person_id=_uuid(person_name),
                    day=d,
                    hours=hours,
                    category=_categories[cat_idx],
                    source="manual",
                    description=f"{_categories[cat_idx].title()} work on {d}",
                )
            )

# ── raw events (sample webhook payloads) ───────────────────────────
RAW_EVENTS: list[RawEvent] = []
for item in ITEMS[:3]:  # create raw events for first 3 work items
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {"key": item.source_id, "fields": {"summary": item.title}},
    }
    RAW_EVENTS.append(
        RawEvent(
            id=_uuid(f"evt-{item.source_id}"),
            source=item.source,
            entity_type="issue",
            entity_id=item.source_id,
            occurred_at=item.resolved_at or datetime.now(tz=timezone.utc),
            content_hash=_hash(payload),
            payload=payload,
        )
    )

# ── reports ─────────────────────────────────────────────────────────
REPORTS = [
    Report(
        id=_uuid("report-daily-today"),
        period="daily",
        period_start=today,
        period_end=today,
        title=f"Daily Brief – {today.isoformat()}",
        summary=(
            "Sprint 24 is on track. CASE-110 (CEO report generator) at 40% progress. "
            "1 bug (CASE-113) flagged as high priority. Team logged 26h yesterday."
        ),
        metrics={
            "sprint_id": str(_uuid("sprint-24")),
            "velocity_current": 0,
            "velocity_target": 20,
            "items_open": 3,
            "items_in_progress": 2,
            "items_review": 1,
            "items_done": 0,
            "total_effort_hours_yesterday": 26.0,
            "overdue_count": 0,
        },
    ),
    Report(
        id=_uuid("report-weekly-prev"),
        period="weekly",
        period_start=sprint_start - timedelta(weeks=1),
        period_end=sprint_start - timedelta(days=1),
        title=f"Weekly Summary – w/c {(sprint_start - timedelta(weeks=1)).isoformat()}",
        summary=(
            "Sprint 23 closed successfully. All 3 stories delivered (10 SP). "
            "Average daily effort: 6.2h/person. No blockers carried over."
        ),
        metrics={
            "sprint_id": str(_uuid("sprint-23")),
            "velocity_achieved": 10,
            "stories_completed": 3,
            "bugs_resolved": 0,
            "avg_daily_effort_hours": 6.2,
        },
    ),
]


async def seed() -> None:
    engine = create_async_engine(settings.database_url, echo=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Order matters: parents first
        for obj_list in [PEOPLE, SPRINTS, ITEMS, EFFORT_LOGS, RAW_EVENTS, REPORTS]:
            for obj in obj_list:
                session.add(await session.merge(obj))
            await session.flush()
        await session.commit()

    await engine.dispose()
    print(
        f"Seeded: {len(PEOPLE)} people, {len(SPRINTS)} sprints, "
        f"{len(ITEMS)} work items, {len(EFFORT_LOGS)} effort logs, "
        f"{len(RAW_EVENTS)} raw events, {len(REPORTS)} reports."
    )


if __name__ == "__main__":
    asyncio.run(seed())

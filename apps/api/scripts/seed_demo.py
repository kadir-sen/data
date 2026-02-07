#!/usr/bin/env python3
"""Seed the database with realistic demo data for dashboard development.

Usage:
    python -m scripts.seed_demo          # from apps/api/
    # or:
    uv run python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session, engine, Base
from app.models.effort_log import EffortLog
from app.models.person import Person
from app.models.report import Report
from app.models.sprint import Sprint
from app.models.work_item import WorkItem


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NUM_PEOPLE = 8
NUM_SPRINTS = 6
ITEMS_PER_SPRINT = (8, 16)
EFFORT_DAYS_BACK = 60

TEAMS = ["Platform", "Frontend", "Backend", "Data"]
CATEGORIES = ["development", "review", "meeting", "support", "admin", "other"]
ITEM_TYPES = ["epic", "story", "task", "bug", "subtask"]
PRIORITIES = ["critical", "high", "medium", "low"]
STATUSES = ["open", "in_progress", "review", "done", "closed"]

FIRST_NAMES = ["Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Hank"]
LAST_NAMES = ["Chen", "Smith", "Kumar", "Garcia", "Kim", "Nguyen", "Müller", "Silva"]


def _rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(0, delta)))


def _rand_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, random.randint(8, 18), 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def make_people() -> list[Person]:
    people = []
    for i in range(NUM_PEOPLE):
        fn, ln = FIRST_NAMES[i], LAST_NAMES[i]
        people.append(
            Person(
                id=uuid.uuid4(),
                display_name=f"{fn} {ln}",
                email=f"{fn.lower()}.{ln.lower()}@example.com",
                role="member" if i > 0 else "admin",
                team=random.choice(TEAMS),
                source_ids={"jira": f"user-{i}", "gitlab": i + 100},
            )
        )
    return people


def make_sprints() -> list[Sprint]:
    sprints = []
    base = date.today() - timedelta(weeks=NUM_SPRINTS * 2)
    for i in range(NUM_SPRINTS):
        start = base + timedelta(weeks=i * 2)
        end = start + timedelta(days=13)
        status = "closed" if i < NUM_SPRINTS - 2 else ("active" if i == NUM_SPRINTS - 2 else "future")
        sprints.append(
            Sprint(
                id=uuid.uuid4(),
                name=f"Sprint {40 + i}",
                source="jira",
                source_id=f"sprint-{40 + i}",
                board_or_project="PROJ",
                status=status,
                start_date=start,
                end_date=end,
                goal=f"Deliver milestone {i + 1} features",
            )
        )
    return sprints


def make_work_items(sprints: list[Sprint], people: list[Person]) -> list[WorkItem]:
    items = []
    counter = 1
    for sprint in sprints:
        n = random.randint(*ITEMS_PER_SPRINT)
        for _ in range(n):
            item_type = random.choices(ITEM_TYPES, weights=[1, 4, 5, 3, 2])[0]
            sp = random.choice([1, 2, 3, 5, 8, 13]) if item_type in ("story", "task", "bug") else None

            # Determine status based on sprint status
            if sprint.status == "closed":
                status = random.choices(STATUSES, weights=[1, 1, 1, 10, 8])[0]
            elif sprint.status == "active":
                status = random.choices(STATUSES, weights=[2, 5, 3, 3, 1])[0]
            else:
                status = random.choices(STATUSES, weights=[10, 1, 0, 0, 0])[0]

            resolved_at = None
            if status in ("done", "closed") and sprint.start_date and sprint.end_date:
                rd = _rand_date(sprint.start_date, sprint.end_date)
                resolved_at = _rand_datetime(rd)

            # Build realistic changelog for MetricsService
            changelog = []
            status_idx = STATUSES.index(status) if status in STATUSES else 0
            s_start = sprint.start_date or date.today()
            for si in range(status_idx):
                transition_day = s_start + timedelta(days=random.randint(si * 2, si * 2 + 3))
                changelog.append({
                    "field": "status",
                    "from": STATUSES[si],
                    "to": STATUSES[si + 1],
                    "at": _rand_datetime(transition_day).isoformat(),
                })

            items.append(
                WorkItem(
                    id=uuid.uuid4(),
                    source="jira",
                    source_id=f"PROJ-{counter}",
                    title=f"[{item_type.upper()}] Task #{counter} – {random.choice(['Login', 'Dashboard', 'API', 'Cache', 'Auth', 'DB', 'UI', 'CI'])} work",
                    item_type=item_type,
                    status=status,
                    priority=random.choice(PRIORITIES),
                    story_points=sp,
                    due_date=sprint.end_date,
                    resolved_at=resolved_at,
                    assignee_id=random.choice(people).id,
                    sprint_id=sprint.id,
                    labels=[random.choice(["frontend", "backend", "infra", "docs"])],
                    changelog=changelog,
                )
            )
            counter += 1
    return items


def make_effort_logs(people: list[Person], items: list[WorkItem]) -> list[EffortLog]:
    logs = []
    today = date.today()
    for person in people:
        person_items = [i for i in items if i.assignee_id == person.id]
        for day_offset in range(EFFORT_DAYS_BACK):
            d = today - timedelta(days=day_offset)
            if d.weekday() >= 5:  # skip weekends
                continue
            # 1-3 entries per day
            for _ in range(random.randint(1, 3)):
                logs.append(
                    EffortLog(
                        id=uuid.uuid4(),
                        person_id=person.id,
                        day=d,
                        hours=round(random.uniform(0.5, 4.0), 1),
                        category=random.choices(
                            CATEGORIES, weights=[5, 2, 2, 1, 1, 1]
                        )[0],
                        description=f"Work on {random.choice(['feature', 'bugfix', 'review', 'planning', 'docs'])}",
                        work_item_id=random.choice(person_items).id if person_items else None,
                        source="manual",
                    )
                )
    return logs


def make_reports(sprints: list[Sprint]) -> list[Report]:
    reports = []
    for sprint in sprints:
        if sprint.status == "future" or not sprint.start_date or not sprint.end_date:
            continue
        velocity = random.randint(25, 55)
        reports.append(
            Report(
                id=uuid.uuid4(),
                period="weekly",
                period_start=sprint.start_date,
                period_end=sprint.end_date,
                title=f"{sprint.name} Report",
                summary=f"Team delivered {velocity} story points. Focus areas: API, UI, infra.",
                metrics={
                    "velocity": velocity,
                    "burndown_remaining": random.randint(0, 15),
                    "effort_total_hours": round(random.uniform(200, 400), 1),
                    "bugs_opened": random.randint(1, 8),
                    "bugs_closed": random.randint(0, 6),
                    "completion_rate": round(random.uniform(70, 98), 1),
                },
            )
        )
    return reports


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def seed() -> None:
    # Create tables (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        session: AsyncSession

        people = make_people()
        sprints = make_sprints()
        items = make_work_items(sprints, people)
        effort_logs = make_effort_logs(people, items)
        reports = make_reports(sprints)

        session.add_all(people)
        session.add_all(sprints)
        await session.flush()
        session.add_all(items)
        await session.flush()
        session.add_all(effort_logs)
        session.add_all(reports)
        await session.commit()

        print(f"Seeded: {len(people)} people, {len(sprints)} sprints, "
              f"{len(items)} work items, {len(effort_logs)} effort logs, "
              f"{len(reports)} reports")
        print("\nSample sprint IDs (for burndown queries):")
        for s in sprints:
            print(f"  {s.name}: {s.id}  [{s.status}]")


if __name__ == "__main__":
    asyncio.run(seed())

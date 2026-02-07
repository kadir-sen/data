"""Shared test fixtures — in-process SQLite async DB + HTTPX client."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.models.effort_log import EffortLog
from app.models.person import Person
from app.models.report import Report
from app.models.sprint import Sprint
from app.models.work_item import WorkItem
from app.rbac import CurrentUser, Role, get_current_user

# Use aiosqlite for fast, isolated, in-process tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX client wired to the FastAPI app with test DB override."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    # Default: override auth to admin user
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="stub-admin-id", email="admin@test.com", role=Role.ADMIN,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pre-populated data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def person_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
async def seeded_person(db_session: AsyncSession, person_id: uuid.UUID) -> Person:
    p = Person(
        id=person_id,
        display_name="Test User",
        email="test@example.com",
        role="member",
        team="Backend",
        source_ids={"jira": "user-1"},
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
def sprint_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
async def seeded_sprint(db_session: AsyncSession, sprint_id: uuid.UUID) -> Sprint:
    s = Sprint(
        id=sprint_id,
        name="Sprint 42",
        source="jira",
        source_id="sprint-42",
        board_or_project="PROJ",
        status="active",
        start_date=date.today() - timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
        goal="Ship auth module",
    )
    db_session.add(s)
    await db_session.commit()
    return s


@pytest.fixture
async def seeded_work_items(
    db_session: AsyncSession,
    seeded_sprint: Sprint,
    seeded_person: Person,
) -> list[WorkItem]:
    items = []
    for i, status in enumerate(["open", "in_progress", "review", "done", "closed"]):
        wi = WorkItem(
            id=uuid.uuid4(),
            source="jira",
            source_id=f"PROJ-{i + 1}",
            title=f"Task {i + 1}",
            item_type="story",
            status=status,
            priority="high" if i < 2 else "medium",
            story_points=float(i + 1) * 2,
            due_date=seeded_sprint.end_date,
            assignee_id=seeded_person.id,
            sprint_id=seeded_sprint.id,
            resolved_at=(
                datetime.now(tz=timezone.utc) - timedelta(days=i)
                if status in ("done", "closed")
                else None
            ),
            labels=["backend"],
            changelog=[{
                "field": "status",
                "from": "open",
                "to": status,
                "at": (datetime.now(tz=timezone.utc) - timedelta(days=5 - i)).isoformat(),
            }],
        )
        items.append(wi)
    db_session.add_all(items)
    await db_session.commit()
    return items


@pytest.fixture
async def seeded_effort_logs(
    db_session: AsyncSession,
    seeded_person: Person,
    seeded_work_items: list[WorkItem],
) -> list[EffortLog]:
    logs = []
    for day_offset in range(5):
        log = EffortLog(
            id=uuid.uuid4(),
            person_id=seeded_person.id,
            day=date.today() - timedelta(days=day_offset),
            hours=round(4.0 + day_offset * 0.5, 1),
            category="development" if day_offset % 2 == 0 else "review",
            description=f"Day {day_offset} work",
            work_item_id=seeded_work_items[0].id,
            source="manual",
        )
        logs.append(log)
    db_session.add_all(logs)
    await db_session.commit()
    return logs


@pytest.fixture
async def seeded_admin_person(db_session: AsyncSession) -> Person:
    """Person linked to the default admin stub user (email=admin@test.com)."""
    p = Person(
        id=uuid.uuid4(),
        display_name="Admin User",
        email="admin@test.com",
        role="admin",
        team="Backend",
        source_ids={},
    )
    db_session.add(p)
    await db_session.commit()
    return p


def _make_auth_client(db_engine, user_id: str, email: str, role: Role):
    """Factory for creating test clients with a specific auth identity."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def _override_session():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=user_id, email=email, role=role,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()

    return _ctx()


@pytest.fixture
async def member_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a member (test@example.com)."""
    async with _make_auth_client(
        db_engine, "stub-member-id", "test@example.com", Role.MEMBER,
    ) as ac:
        yield ac


@pytest.fixture
async def manager_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a manager (manager@test.com)."""
    async with _make_auth_client(
        db_engine, "stub-manager-id", "manager@test.com", Role.MANAGER,
    ) as ac:
        yield ac


@pytest.fixture
async def seeded_manager_person(db_session: AsyncSession) -> Person:
    """Person linked to the manager test user."""
    p = Person(
        id=uuid.uuid4(),
        display_name="Manager User",
        email="manager@test.com",
        role="manager",
        team="Backend",
        source_ids={},
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def seeded_report(db_session: AsyncSession, seeded_sprint: Sprint) -> Report:
    r = Report(
        id=uuid.uuid4(),
        period="weekly",
        period_start=seeded_sprint.start_date or date.today(),
        period_end=seeded_sprint.end_date or date.today(),
        title="Sprint 42 Report",
        summary="Good progress on auth module.",
        metrics={"velocity": 42, "burndown_remaining": 8, "effort_total_hours": 160},
    )
    db_session.add(r)
    await db_session.commit()
    return r

"""metric_snapshot – daily materialized metrics + sprint burndown points."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MetricSnapshotDaily(Base):
    """One row per (date, team, sprint) with pre-computed metrics JSON."""

    __tablename__ = "metric_snapshot_daily"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    team_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="Person.team value; NULL = org-wide"
    )
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sprint.id"), nullable=True
    )
    metrics_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Velocity, burndown summary, flow, throughput, due-date risk, etc.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sprint = relationship("Sprint", lazy="selectin")

    __table_args__ = (
        Index("ix_metric_snapshot_date_team_sprint", "date", "team_id", "sprint_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MetricSnapshotDaily {self.date} team={self.team_id} sprint={self.sprint_id}>"


class SprintBurndownPoint(Base):
    """One row per (date, sprint) recording remaining vs completed work."""

    __tablename__ = "sprint_burndown_point"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sprint.id"), nullable=False
    )
    remaining: Mapped[float] = mapped_column(Float, nullable=False, comment="Story points remaining")
    completed: Mapped[float] = mapped_column(Float, nullable=False, comment="Story points completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sprint = relationship("Sprint", lazy="selectin")

    __table_args__ = (
        Index("ix_burndown_sprint_date", "sprint_id", "date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<SprintBurndownPoint {self.date} sprint={self.sprint_id} rem={self.remaining}>"

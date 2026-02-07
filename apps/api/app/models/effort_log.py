"""effort_log – employee effort declarations (manual + imported)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class EffortLog(Base):
    __tablename__ = "effort_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="development",
        comment="development|review|meeting|support|admin|other",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_item.id"), nullable=True
    )
    planned_hours: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Planned hours for planned-vs-actual tracking"
    )
    locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Locked days cannot be edited"
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="manual", comment="manual|jira_tempo|gitlab_time|csv"
    )
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Source-specific fields")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    person = relationship("Person", back_populates="effort_logs")
    work_item = relationship("WorkItem", lazy="selectin")

    __table_args__ = (
        Index("ix_effort_log_person_day", "person_id", "day"),
    )

    def __repr__(self) -> str:
        return f"<EffortLog {self.person_id} {self.day} {self.hours}h>"

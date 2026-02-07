"""work_item – normalized issues/tasks from Jira, GitLab, Notion."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WorkItem(Base):
    __tablename__ = "work_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, comment="jira|gitlab|notion")
    source_id: Mapped[str] = mapped_column(String(256), nullable=False, comment="Source-native ID (e.g. PROJ-123)")
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="task", comment="epic|story|task|bug|subtask"
    )
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="open", comment="open|in_progress|review|done|closed"
    )
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="critical|high|medium|low")
    story_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # foreign keys
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), nullable=True
    )
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sprint.id"), nullable=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_item.id"), nullable=True, comment="Epic / parent item"
    )

    labels: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    changelog: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Status transition history for burndown/velocity calc",
    )
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Source-specific fields")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relationships
    assignee = relationship("Person", back_populates="work_items")
    sprint = relationship("Sprint", back_populates="work_items")
    parent = relationship("WorkItem", remote_side="WorkItem.id", lazy="selectin")

    __table_args__ = (
        Index("ix_work_item_due_status_sprint_assignee", "due_date", "status", "sprint_id", "assignee_id"),
        Index("ix_work_item_source_source_id", "source", "source_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<WorkItem {self.source}/{self.source_id} [{self.status}]>"

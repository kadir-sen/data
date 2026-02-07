"""interaction_event – Slack messages, PR/issue comments, review comments."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class InteractionEvent(Base):
    __tablename__ = "interaction_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="slack|jira|gitlab|github|confluence"
    )
    source_id: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="Source-native message/comment ID"
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="message",
        comment="message|comment|review|reaction|thread_reply",
    )
    channel_or_context: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="Slack channel, PR URL, issue key – the context for the interaction",
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), nullable=True
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_item.id"), nullable=True,
        comment="Linked work item if this is a comment on a ticket",
    )
    doc_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doc_entry.id"), nullable=True,
        comment="Linked doc if this is a comment on a page",
    )
    parent_interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interaction_event.id"), nullable=True,
        comment="Thread parent for threaded conversations",
    )
    extra: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Source-specific fields"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the interaction happened"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    author = relationship("Person", lazy="selectin")
    work_item = relationship("WorkItem", lazy="selectin")
    doc_entry = relationship("DocEntry", lazy="selectin")
    parent_interaction = relationship(
        "InteractionEvent", remote_side="InteractionEvent.id", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_interaction_source_source_id", "source", "source_id", unique=True),
        Index("ix_interaction_occurred", "occurred_at"),
        Index("ix_interaction_work_item", "work_item_id"),
    )

    def __repr__(self) -> str:
        return f"<InteractionEvent {self.source}/{self.event_type} {self.source_id}>"

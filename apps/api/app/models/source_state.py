"""source_state – per-source cursor tracking for incremental sync.

Stores the last successful sync timestamp and optional pagination cursor
for each (source, entity_type) pair. This allows connectors to resume
from where they left off, ensuring incremental sync is both efficient
and idempotent.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SourceState(Base):
    __tablename__ = "source_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="jira|gitlab|slack|notion|confluence|google_meet"
    )
    entity_type: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="issue|mr|page|message|transcript|sprint|…"
    )
    last_run: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Timestamp of last successful sync"
    )
    cursor: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Opaque pagination cursor for resumption"
    )
    extra: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional state (e.g. board_id, channel list)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_source_state_source_entity", "source", "entity_type", unique=True),
    )

    def __repr__(self) -> str:
        return f"<SourceState {self.source}/{self.entity_type} last_run={self.last_run}>"

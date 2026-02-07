"""raw_event – append-only ingestion log, idempotent via content hash."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RawEvent(Base):
    __tablename__ = "raw_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, comment="jira|gitlab|notion|manual")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="issue|mr|page|sprint|…")
    entity_id: Mapped[str] = mapped_column(String(256), nullable=False, comment="Source-native ID")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="SHA-256 for idempotency"
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="Full webhook / API body")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Processing error if any")

    __table_args__ = (
        Index("ix_raw_event_source_entity_occurred", "source", "entity_id", "occurred_at"),
    )

    def __repr__(self) -> str:
        return f"<RawEvent {self.source}/{self.entity_type}/{self.entity_id}>"

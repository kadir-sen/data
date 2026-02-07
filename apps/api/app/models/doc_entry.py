"""doc_entry – Confluence pages, Notion docs, Google Meet transcripts."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DocEntry(Base):
    __tablename__ = "doc_entry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="confluence|notion|google_meet"
    )
    source_id: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="Source-native page/doc ID"
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="page",
        comment="page|transcript|meeting_notes|design_doc",
    )
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    body_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Plain-text / markdown body for search"
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), nullable=True
    )
    space_or_parent: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="Confluence space key / Notion parent DB"
    )
    labels: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    extra: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Source-specific fields"
    )
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Meeting time / publish date"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relationships
    author = relationship("Person", lazy="selectin")

    __table_args__ = (
        Index("ix_doc_entry_source_source_id", "source", "source_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<DocEntry {self.source}/{self.source_id} {self.title!r}>"

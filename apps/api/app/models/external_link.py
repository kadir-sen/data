"""external_link – cross-system identity mapping for the same logical entity."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExternalLink(Base):
    __tablename__ = "external_link"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The canonical entity this link points to
    canonical_table: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="work_item|sprint|person|doc_entry",
    )
    canonical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="PK in the canonical table"
    )
    # The external reference
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="jira|gitlab|notion|confluence|slack"
    )
    external_id: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="ID in the external system"
    )
    external_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True, comment="Deep link to the entity in the source"
    )
    link_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="auto",
        comment="auto|manual – how the link was established",
    )
    confidence: Mapped[float | None] = mapped_column(
        nullable=True, comment="0.0-1.0 confidence for heuristic links"
    )
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_ext_link_canonical", "canonical_table", "canonical_id"),
        Index(
            "ix_ext_link_source_external",
            "source", "external_id", "canonical_table",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExternalLink {self.source}/{self.external_id} "
            f"-> {self.canonical_table}/{self.canonical_id}>"
        )

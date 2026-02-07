"""sprint – canonical sprint / milestone table."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Sprint(Base):
    __tablename__ = "sprint"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, comment="jira|gitlab")
    source_id: Mapped[str] = mapped_column(String(256), nullable=False, comment="Jira sprint ID or GitLab milestone ID")
    board_or_project: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="future", comment="future|active|closed"
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    goal: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Source-specific fields")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relationships
    work_items = relationship("WorkItem", back_populates="sprint", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Sprint {self.name!r} [{self.status}]>"

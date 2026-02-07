"""report – daily/weekly/monthly CEO briefs + metrics JSON."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Report(Base):
    __tablename__ = "report"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    period: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="daily|weekly|monthly"
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Human-readable brief")
    metrics: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Structured KPIs: velocity, burndown, effort totals, etc.",
    )
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Auxiliary data")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # fast lookup by period type + date range
    )

    def __repr__(self) -> str:
        return f"<Report {self.period} {self.period_start}..{self.period_end}>"

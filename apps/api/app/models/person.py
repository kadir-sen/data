"""person – unified user/team identity across sources."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Person(Base):
    __tablename__ = "person"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(
        String(64), nullable=False, default="member", comment="admin|manager|member|bot"
    )
    team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_ids: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment='{"jira": "acc-id", "gitlab": 42, "notion": "uuid"}',
    )
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Source-specific fields")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relationships
    work_items = relationship("WorkItem", back_populates="assignee", lazy="selectin")
    effort_logs = relationship("EffortLog", back_populates="person", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Person {self.display_name!r}>"

"""audit_log – immutable record of security-relevant events."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="User who performed the action (NULL for system events)",
    )
    action: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
        comment="e.g. token.created, token.used, token.rotated, auth.login, auth.logout",
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="e.g. source_token, user, connector",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="ID of the affected resource",
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human-readable summary",
    )
    meta: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Structured data: IP, user-agent, scopes, etc.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action!r} actor={self.actor_id}>"

"""user – application authentication user (separate from person/identity)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="bcrypt hash; NULL for OAuth-only users"
    )
    role: Mapped[str] = mapped_column(
        String(64), nullable=False, default="member",
        comment="admin | manager | member",
    )
    auth_provider: Mapped[str] = mapped_column(
        String(64), nullable=False, default="local",
        comment="local | google",
    )
    google_sub: Mapped[str | None] = mapped_column(
        String(256), unique=True, nullable=True,
        comment="Google 'sub' claim for OAuth users",
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role}>"

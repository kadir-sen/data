"""source_token – encrypted vault for third-party API tokens.

Token scopes required per source:
───────────────────────────────────────────────────────────────────
Jira Cloud
  - read:jira-work          Read issues, boards, sprints
  - read:jira-user          Read user profiles for assignee mapping
  - write:jira-work         (optional) Create/update issues

GitLab
  - read_api                Read projects, issues, merge requests, time tracking
  - read_user               Read user profile for identity mapping
  - api                     (optional) Full API access for write operations

Slack
  - channels:read           List channels for activity correlation
  - users:read              Map Slack users to Person records
  - chat:read               (optional) Read messages for keyword extraction

Notion
  - read_content            Read pages, databases, and blocks
  - read_users              Read workspace member list

Google Workspace (Calendar/Drive)
  - https://www.googleapis.com/auth/calendar.readonly
  - https://www.googleapis.com/auth/drive.metadata.readonly
───────────────────────────────────────────────────────────────────

Encryption: AES-256-GCM with per-row random nonce.  The encrypted blob
is stored as   nonce (12 B) || ciphertext || tag (16 B)   in a single
LargeBinary column.  See app/crypto.py for encrypt/decrypt helpers.

Rotation: When VAULT_ENCRYPTION_KEY changes, set the old key as
VAULT_ENCRYPTION_KEY_PREVIOUS.  Reads try the primary key first, then
the previous key.  A background re-encrypt job migrates rows forward.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SourceToken(Base):
    __tablename__ = "source_token"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="jira | gitlab | slack | notion | google",
    )
    label: Mapped[str] = mapped_column(
        String(256), nullable=False, default="",
        comment="Human-readable label, e.g. 'Acme Jira Cloud'",
    )
    encrypted_token: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False,
        comment="AES-256-GCM: nonce(12) || ciphertext || tag(16)",
    )
    scopes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Comma-separated scopes granted by the user",
    )
    is_service_account: Mapped[bool] = mapped_column(
        default=False, nullable=False,
        comment="True if this token is the org-wide service account for background jobs",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SourceToken {self.source!r} user={self.user_id}>"

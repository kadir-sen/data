"""Auth tables – app_user, source_token (encrypted vault), audit_log.

Revision ID: 002
Revises: 001
Create Date: 2026-02-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── app_user ──────────────────────────────────────────────────
    op.create_table(
        "app_user",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column(
            "password_hash", sa.String(256), nullable=True,
            comment="bcrypt hash; NULL for OAuth-only users",
        ),
        sa.Column(
            "role", sa.String(64), nullable=False, server_default="member",
            comment="admin | manager | member",
        ),
        sa.Column(
            "auth_provider", sa.String(64), nullable=False, server_default="local",
            comment="local | google",
        ),
        sa.Column(
            "google_sub", sa.String(256), unique=True, nullable=True,
            comment="Google 'sub' claim for OAuth users",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"])

    # ── source_token (vault) ──────────────────────────────────────
    op.create_table(
        "source_token",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "source", sa.String(64), nullable=False,
            comment="jira | gitlab | slack | notion | google",
        ),
        sa.Column(
            "label", sa.String(256), nullable=False, server_default="",
            comment="Human-readable label",
        ),
        sa.Column(
            "encrypted_token", sa.LargeBinary, nullable=False,
            comment="AES-256-GCM: nonce(12) || ciphertext || tag(16)",
        ),
        sa.Column(
            "scopes", sa.Text, nullable=True,
            comment="Comma-separated scopes granted by the user",
        ),
        sa.Column(
            "is_service_account", sa.Boolean, nullable=False, server_default=sa.text("false"),
            comment="True → org-wide token for background jobs",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_source_token_user_source", "source_token", ["user_id", "source"])

    # ── audit_log ─────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id", UUID(as_uuid=True), nullable=True,
            comment="User who performed the action (NULL for system events)",
        ),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(256), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("source_token")
    op.drop_table("app_user")

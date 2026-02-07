"""Add doc_entry, interaction_event, external_link tables.

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
    # ── doc_entry ─────────────────────────────────────────────────────
    op.create_table(
        "doc_entry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(256), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False, server_default="page"),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("body_text", sa.Text, nullable=True),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("space_or_parent", sa.String(256), nullable=True),
        sa.Column("labels", JSONB, nullable=True, server_default="[]"),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_doc_entry_source_source_id",
        "doc_entry",
        ["source", "source_id"],
        unique=True,
    )

    # ── interaction_event ─────────────────────────────────────────────
    op.create_table(
        "interaction_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(256), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False, server_default="message"),
        sa.Column("channel_or_context", sa.String(256), nullable=True),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("work_item_id", UUID(as_uuid=True), sa.ForeignKey("work_item.id"), nullable=True),
        sa.Column("doc_entry_id", UUID(as_uuid=True), sa.ForeignKey("doc_entry.id"), nullable=True),
        sa.Column("parent_interaction_id", UUID(as_uuid=True), sa.ForeignKey("interaction_event.id"), nullable=True),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_interaction_source_source_id",
        "interaction_event",
        ["source", "source_id"],
        unique=True,
    )
    op.create_index("ix_interaction_occurred", "interaction_event", ["occurred_at"])
    op.create_index("ix_interaction_work_item", "interaction_event", ["work_item_id"])

    # ── external_link ─────────────────────────────────────────────────
    op.create_table(
        "external_link",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_table", sa.String(64), nullable=False),
        sa.Column("canonical_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("external_url", sa.String(2048), nullable=True),
        sa.Column("link_type", sa.String(32), nullable=False, server_default="auto"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_ext_link_canonical",
        "external_link",
        ["canonical_table", "canonical_id"],
    )
    op.create_index(
        "ix_ext_link_source_external",
        "external_link",
        ["source", "external_id", "canonical_table"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("external_link")
    op.drop_table("interaction_event")
    op.drop_table("doc_entry")

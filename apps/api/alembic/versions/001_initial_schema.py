"""Initial schema – raw_event, person, sprint, work_item, effort_log, report.

Revision ID: 001
Revises: None
Create Date: 2025-02-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── raw_event ────────────────────────────────────────────────────
    op.create_table(
        "raw_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(256), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_raw_event_source_entity_occurred",
        "raw_event",
        ["source", "entity_id", "occurred_at"],
    )

    # ── person ───────────────────────────────────────────────────────
    op.create_table(
        "person",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("email", sa.String(320), unique=True, nullable=True),
        sa.Column("role", sa.String(64), nullable=False, server_default="member"),
        sa.Column("team", sa.String(128), nullable=True),
        sa.Column("source_ids", JSONB, nullable=False, server_default="{}"),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── sprint ───────────────────────────────────────────────────────
    op.create_table(
        "sprint",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(256), nullable=False),
        sa.Column("board_or_project", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="future"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("goal", sa.String(1024), nullable=True),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── work_item ────────────────────────────────────────────────────
    op.create_table(
        "work_item",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(256), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("item_type", sa.String(64), nullable=False, server_default="task"),
        sa.Column("status", sa.String(64), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(32), nullable=True),
        sa.Column("story_points", sa.Float, nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assignee_id", UUID(as_uuid=True), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("sprint_id", UUID(as_uuid=True), sa.ForeignKey("sprint.id"), nullable=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("work_item.id"), nullable=True),
        sa.Column("labels", JSONB, nullable=True, server_default="[]"),
        sa.Column("changelog", JSONB, nullable=True, server_default="[]"),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_work_item_due_status_sprint_assignee",
        "work_item",
        ["due_date", "status", "sprint_id", "assignee_id"],
    )
    op.create_index(
        "ix_work_item_source_source_id",
        "work_item",
        ["source", "source_id"],
        unique=True,
    )

    # ── effort_log ───────────────────────────────────────────────────
    op.create_table(
        "effort_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("hours", sa.Float, nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="development"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("work_item_id", UUID(as_uuid=True), sa.ForeignKey("work_item.id"), nullable=True),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_effort_log_person_day",
        "effort_log",
        ["person_id", "day"],
    )

    # ── report ───────────────────────────────────────────────────────
    op.create_table(
        "report",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("metrics", JSONB, nullable=False, server_default="{}"),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report")
    op.drop_table("effort_log")
    op.drop_table("work_item")
    op.drop_table("sprint")
    op.drop_table("person")
    op.drop_table("raw_event")

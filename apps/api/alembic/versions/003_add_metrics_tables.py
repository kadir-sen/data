"""Add metric_snapshot_daily and sprint_burndown_point tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── metric_snapshot_daily ─────────────────────────────────────
    op.create_table(
        "metric_snapshot_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("team_id", sa.String(128), nullable=True),
        sa.Column("sprint_id", UUID(as_uuid=True), sa.ForeignKey("sprint.id"), nullable=True),
        sa.Column("metrics_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_metric_snapshot_date_team_sprint",
        "metric_snapshot_daily",
        ["date", "team_id", "sprint_id"],
        unique=True,
    )

    # ── sprint_burndown_point ─────────────────────────────────────
    op.create_table(
        "sprint_burndown_point",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("sprint_id", UUID(as_uuid=True), sa.ForeignKey("sprint.id"), nullable=False),
        sa.Column("remaining", sa.Float, nullable=False),
        sa.Column("completed", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_burndown_sprint_date",
        "sprint_burndown_point",
        ["sprint_id", "date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("sprint_burndown_point")
    op.drop_table("metric_snapshot_daily")

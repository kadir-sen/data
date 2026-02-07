"""Add source_state table for incremental sync cursor tracking.

Revision ID: 004
Revises: 003
Create Date: 2026-02-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_state",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cursor", sa.Text, nullable=True),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_source_state_source_entity",
        "source_state",
        ["source", "entity_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("source_state")

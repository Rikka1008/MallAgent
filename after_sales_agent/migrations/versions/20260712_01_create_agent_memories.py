"""create agent memories

Revision ID: 20260712_01
Revises:
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260712_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("agent_memories",
        sa.Column("namespace", sa.String(length=256), nullable=False),
        sa.Column("memory_key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("namespace", "memory_key"),
    )


def downgrade() -> None:
    op.drop_table("agent_memories")

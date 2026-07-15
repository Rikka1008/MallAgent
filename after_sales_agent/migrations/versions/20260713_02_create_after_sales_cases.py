"""create after sales cases

Revision ID: 20260713_02
Revises: 20260712_01
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260713_02"
down_revision: str | None = "20260712_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "after_sales_cases",
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index("ix_after_sales_cases_user_session", "after_sales_cases", ["user_id", "session_id"])
    op.create_table(
        "after_sales_case_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["case_id"], ["after_sales_cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_after_sales_case_events_case_id", "after_sales_case_events", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_after_sales_case_events_case_id", table_name="after_sales_case_events")
    op.drop_table("after_sales_case_events")
    op.drop_index("ix_after_sales_cases_user_session", table_name="after_sales_cases")
    op.drop_table("after_sales_cases")

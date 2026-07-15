"""create agent conversations

Revision ID: 20260715_03
Revises: 20260713_02
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260715_03"
down_revision: str | None = "20260713_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("summary_status", sa.String(length=16), nullable=False, server_default="not_started"),
        sa.Column("close_reason", sa.String(length=32), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("summary_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("next_summary_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','closed')", name="ck_agent_conversations_status"),
        sa.CheckConstraint("summary_status IN ('not_started','pending','processing','completed','failed')", name="ck_agent_conversations_summary_status"),
        sa.CheckConstraint("close_reason IS NULL OR close_reason IN ('idle_timeout','user_new_session','replaced','admin','retention_cleanup')", name="ck_agent_conversations_close_reason"),
        sa.CheckConstraint("message_count >= 0", name="ck_agent_conversations_message_count"),
        sa.CheckConstraint("summary_attempts BETWEEN 0 AND 3", name="ck_agent_conversations_summary_attempts"),
        sa.CheckConstraint("(status = 'active' AND closed_at IS NULL AND close_reason IS NULL AND expires_at IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL AND close_reason IS NOT NULL AND expires_at IS NOT NULL)", name="ck_agent_conversations_lifecycle"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index("uq_agent_conversations_active_user", "agent_conversations", ["user_id"], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_agent_conversations_idle", "agent_conversations", ["last_active_at"], postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_agent_conversations_summary_due", "agent_conversations", ["next_summary_attempt_at", "closed_at"], postgresql_where=sa.text("summary_status IN ('pending','failed')"))
    op.create_index("ix_agent_conversations_recall", "agent_conversations", ["user_id", sa.text("closed_at DESC")], postgresql_where=sa.text("summary_status = 'completed'"))
    op.create_index("ix_agent_conversations_cleanup", "agent_conversations", ["expires_at"], postgresql_where=sa.text("status = 'closed'"))


def downgrade() -> None:
    op.drop_index("ix_agent_conversations_cleanup", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_recall", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_summary_due", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_idle", table_name="agent_conversations")
    op.drop_index("uq_agent_conversations_active_user", table_name="agent_conversations")
    op.drop_table("agent_conversations")

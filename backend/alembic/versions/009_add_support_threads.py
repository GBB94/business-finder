"""Add support_threads table for Phase 3 support agent

Revision ID: 009
Revises: 008
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=False),
        sa.Column("customer_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("messages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("escalation_reason", sa.String(500), nullable=True),
        sa.Column("feature_request_extracted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id"), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_support_threads_launch_id", "support_threads", ["launch_id"])
    op.create_index("ix_support_threads_launch_email", "support_threads", ["launch_id", "customer_email"])


def downgrade() -> None:
    op.drop_index("ix_support_threads_launch_email", table_name="support_threads")
    op.drop_index("ix_support_threads_launch_id", table_name="support_threads")
    op.drop_table("support_threads")

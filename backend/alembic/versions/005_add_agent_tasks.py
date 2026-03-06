"""Add agent_tasks and agent_task_steps tables

Revision ID: 005
Revises: 004
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=True, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("input_params", sa.JSON, nullable=True),
        sa.Column("output", sa.JSON, nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("claimed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "agent_task_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("step_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("input_data", sa.JSON, nullable=True),
        sa.Column("output_data", sa.JSON, nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )


def downgrade():
    op.drop_table("agent_task_steps")
    op.drop_table("agent_tasks")

"""Add metric_entries table

Revision ID: 002
Revises: 001
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "metric_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("metric_key", sa.String(50), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=True),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("idea_id", "metric_key", "period_start", name="uq_idea_metric_period"),
    )


def downgrade():
    op.drop_table("metric_entries")

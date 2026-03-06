"""Add score_history table and ideas.archive_note column

Revision ID: 003
Revises: 002
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "score_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("dimensions_snapshot", sa.JSON, nullable=True),
        sa.Column("weighted_total", sa.Float, nullable=True),
        sa.Column("snapshot_at", sa.DateTime, nullable=False),
    )

    op.add_column("ideas", sa.Column("archive_note", sa.Text, nullable=True))


def downgrade():
    op.drop_column("ideas", "archive_note")
    op.drop_table("score_history")

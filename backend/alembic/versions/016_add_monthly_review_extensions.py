"""Add speed-mode fields to monthly_reviews.

Adds review_type (monthly/biweekly), score_confidence_snapshot, and the
graduate_to_standard decision option.
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monthly_reviews",
        sa.Column("review_type", sa.String(10), nullable=False, server_default="monthly"),
    )
    op.add_column(
        "monthly_reviews",
        sa.Column("score_confidence_snapshot", sa.JSON, nullable=True),
    )
    op.execute("ALTER TYPE reviewdecision ADD VALUE IF NOT EXISTS 'graduate_to_standard'")


def downgrade() -> None:
    op.drop_column("monthly_reviews", "review_type")
    op.drop_column("monthly_reviews", "score_confidence_snapshot")
    # Cannot remove enum values in Postgres. graduate_to_standard is harmless if unused.

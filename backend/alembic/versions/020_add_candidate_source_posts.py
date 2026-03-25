"""Add candidate_source_posts table.

Provenance records linking CandidateIdeas to their source community posts.
No verbatim body stored. Subject to reddit_purge.py deletion compliance.
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_source_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(36),
            sa.ForeignKey("candidate_ideas.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("subreddit", sa.String(100), nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("relevance_score", sa.Integer, nullable=True),
        sa.Column("engagement_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("content_purged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("purge_reason", sa.String(500), nullable=True),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("candidate_source_posts")

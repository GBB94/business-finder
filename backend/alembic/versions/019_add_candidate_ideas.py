"""Add candidate_ideas table.

Stores discovery pipeline candidates before they are promoted to full Ideas.
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_ideas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_review"),
        # Signal fields
        sa.Column("problem_signal", sa.Text, nullable=False),
        sa.Column("target_audience", sa.Text, nullable=False),
        sa.Column("pain_intensity_score", sa.Float, nullable=True),
        sa.Column("pain_type", sa.String(30), nullable=True),
        sa.Column("evidence_summary", sa.Text, nullable=True),
        sa.Column("source_communities", sa.JSON, nullable=True),
        sa.Column("cross_community", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("spending_signals", sa.JSON, nullable=True),
        sa.Column("competitor_mentions", sa.JSON, nullable=True),
        sa.Column("competition_signal", sa.String(20), nullable=True),
        sa.Column("raw_themes", sa.JSON, nullable=True),
        sa.Column("sample_post_count", sa.Integer, nullable=False, server_default="0"),
        # Evaluation
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("model_version", sa.String(100), nullable=True),
        # Founder suggestion
        sa.Column("founder_note", sa.Text, nullable=True),
        sa.Column("suggested_solution", sa.Text, nullable=True),
        # Lifecycle
        sa.Column("scan_job_id", sa.String(36), nullable=True),
        sa.Column("promoted_idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("dismiss_reason", sa.String(30), nullable=True),
        sa.Column("derived_content_purged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_candidate_ideas_status", "candidate_ideas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_candidate_ideas_status", "candidate_ideas")
    op.drop_table("candidate_ideas")

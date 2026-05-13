"""Add email_suppressions table.

Per-tenant suppression list. Everything depends on suppression screening,
so this migration comes first in the marketing batch.
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_suppressions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("source_provider", sa.String(30), nullable=True),
        sa.Column("source_campaign_id", sa.String(36), nullable=True),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("synced_to_smartlead", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("synced_at", sa.DateTime, nullable=True),
        sa.Column("suppressed_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_email_suppressions_user_email",
        "email_suppressions",
        ["user_id", "email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("email_suppressions")

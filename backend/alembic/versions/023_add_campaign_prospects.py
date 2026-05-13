"""Add campaign_prospects table.

Individual contacts within a Smartlead campaign. Unique on (campaign_id, email).
"""

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_prospects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "campaign_id", sa.String(36),
            sa.ForeignKey("marketing_campaigns.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=True, index=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("personalization_context", sa.String(2000), nullable=True),
        sa.Column("source", sa.String(30), nullable=True),
        sa.Column("provider_lead_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sequence_step", sa.Integer, nullable=False, server_default="1"),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("replied_at", sa.DateTime, nullable=True),
        sa.Column("bounced_at", sa.DateTime, nullable=True),
        sa.Column("reply_promoted_to_evidence", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_campaign_prospect_email",
        "campaign_prospects",
        ["campaign_id", "email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("campaign_prospects")

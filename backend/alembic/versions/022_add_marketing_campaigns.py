"""Add marketing_campaigns table.

Tracks Smartlead cold outbound and social campaigns per idea/launch.
Includes compliance checklist fields and approval workflow columns.
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False, server_default="cold_email"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        # Audience & compliance
        sa.Column("audience_type", sa.String(30), nullable=True),
        sa.Column("target_countries", sa.JSON, nullable=True),
        sa.Column("cold_email_allowed", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("compliance_blocks", sa.JSON, nullable=True),
        # Smartlead
        sa.Column("provider", sa.String(30), nullable=False, server_default="smartlead"),
        sa.Column("provider_campaign_id", sa.String(100), nullable=True),
        sa.Column("smartlead_email_account_id", sa.String(100), nullable=True),
        sa.Column("daily_limit", sa.Integer, nullable=False, server_default="20"),
        sa.Column("sequence_steps", sa.Integer, nullable=False, server_default="3"),
        # Stats
        sa.Column("total_prospects", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_delivered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_bounced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_replied", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_unsubscribed", sa.Integer, nullable=False, server_default="0"),
        # Compliance checklist
        sa.Column("dns_authenticated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dmarc_policy", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("domain_warmup_complete", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("list_unsubscribe_header_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("commercial_ad_disclosure_present", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("physical_address_included", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("unsubscribe_link_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("audience_type_confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("suppression_list_screened", sa.Boolean, nullable=False, server_default="false"),
        # Approval
        sa.Column("approval_token_hash", sa.String(64), nullable=True),
        sa.Column("approval_artifact_id", sa.String(255), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime, nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("rejected_at", sa.DateTime, nullable=True),
        sa.Column("rejection_reason", sa.String(500), nullable=True),
        sa.Column("grant_id", sa.String(36), nullable=True),
        # Social
        sa.Column("platforms", sa.JSON, nullable=True),
        sa.Column("post_content", sa.String(5000), nullable=True),
        sa.Column("scheduled_at", sa.DateTime, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("marketing_campaigns")

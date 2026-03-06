"""Add project_secrets table

Revision ID: 006
Revises: 005
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("key_name", sa.String(255), nullable=False),
        sa.Column("encrypted_value", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("idea_id", "environment", "key_name", name="uq_secret_idea_env_key"),
    )


def downgrade():
    op.drop_table("project_secrets")

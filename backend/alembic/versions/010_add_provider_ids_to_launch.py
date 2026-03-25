"""Add provider IDs to launch_instances for credential isolation.

Render service_id needed to update env vars during promotion.
Neon project_id and preview branch_id needed to manage DB branches.
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("launch_instances", sa.Column("render_service_id", sa.String(100), nullable=True))
    op.add_column("launch_instances", sa.Column("neon_project_id", sa.String(100), nullable=True))
    op.add_column("launch_instances", sa.Column("neon_preview_branch_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("launch_instances", "neon_preview_branch_id")
    op.drop_column("launch_instances", "neon_project_id")
    op.drop_column("launch_instances", "render_service_id")

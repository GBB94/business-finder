"""Add outbound pause columns to launch_instances.

When bounce rate exceeds the threshold, outbound_paused_at is set and
all marketing email tasks are blocked until manually unpaused.
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("launch_instances", sa.Column("outbound_paused_at", sa.DateTime, nullable=True))
    op.add_column("launch_instances", sa.Column("outbound_pause_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("launch_instances", "outbound_pause_reason")
    op.drop_column("launch_instances", "outbound_paused_at")

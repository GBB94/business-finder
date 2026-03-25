"""Add working_branch to launch_instances.

Stores the Git branch name created by the scaffold step so the promote
step knows which ref to merge into main.

Split out from 010 because environments that already applied the
original 010 would not pick up columns added by editing it.
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("launch_instances", sa.Column("working_branch", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("launch_instances", "working_branch")

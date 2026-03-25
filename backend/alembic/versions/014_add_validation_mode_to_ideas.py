"""Add validation_mode to ideas.

Allows ideas to run in 'speed' mode with compressed timelines and
tighter kill triggers, or 'standard' mode (the default).
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ideas",
        sa.Column(
            "validation_mode",
            sa.String(10),
            nullable=False,
            server_default="standard",
        ),
    )
    op.create_index("ix_ideas_validation_mode", "ideas", ["validation_mode"])


def downgrade() -> None:
    op.drop_index("ix_ideas_validation_mode", "ideas")
    op.drop_column("ideas", "validation_mode")

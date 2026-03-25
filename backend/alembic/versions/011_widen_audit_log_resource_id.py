"""Widen audit_log.resource_id from 36 to 255 chars.

Secret-read audit entries store env file paths in resource_id, which
exceed the 36-char UUID limit and would fail on Postgres.
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "resource_id",
        existing_type=sa.String(36),
        type_=sa.String(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "resource_id",
        existing_type=sa.String(255),
        type_=sa.String(36),
        existing_nullable=True,
    )

"""Add provider_event_id column and unique partial index to operational_events

Revision ID: 008
Revises: 007
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "operational_events",
        sa.Column("provider_event_id", sa.String(255), nullable=True),
    )
    # Partial unique index: only enforced when provider_event_id is not null.
    # This prevents concurrent webhook retries from inserting duplicate events.
    op.execute(
        "CREATE UNIQUE INDEX ix_operational_events_provider_event "
        "ON operational_events (launch_id, provider_event_id) "
        "WHERE provider_event_id IS NOT NULL"
    )


def downgrade():
    op.drop_index("ix_operational_events_provider_event", table_name="operational_events")
    op.drop_column("operational_events", "provider_event_id")
